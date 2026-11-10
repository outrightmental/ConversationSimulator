# SPDX-License-Identifier: Apache-2.0
"""The spoken line is decoded from the model's JSON as it arrives (#538)."""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest
import yaml

from convsim_core.runtime import scripted
from convsim_core.services.utterance_stream import SentenceGate, UtteranceStreamExtractor
from convsim_prompt.output_validator import OutputValidationResult, OutputViolation

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKS = REPO_ROOT / "packs" / "official"


def _decode_all(encoded: str, split_at: int) -> tuple[str, bool]:
    ex = UtteranceStreamExtractor()
    out = ex.feed(encoded[:split_at]) + ex.feed(encoded[split_at:])
    return out, ex.done


def _turn_json(line: str, **kw) -> str:
    body = {"npc_utterance": line, "npc_emotion": "warm", "state_delta": {"trust": 2}}
    body.update(kw)
    return json.dumps(body, **({"ensure_ascii": kw.pop("ensure_ascii")} if "ensure_ascii" in kw else {}))


def _all_spoken_lines() -> list[str]:
    lines: list[str] = []
    for entry in scripted._FIRST_WORDS_SCRIPT:
        lines.append(entry["npc_utterance"])
    for name in dir(scripted):
        value = getattr(scripted, name)
        if isinstance(value, dict) and "npc_utterance" in value:
            lines.append(value["npc_utterance"])
        if isinstance(value, dict):
            for v in value.values():
                if isinstance(v, dict) and "npc_utterance" in v:
                    lines.append(v["npc_utterance"])
    for path in PACKS.glob("*/scenarios/*.yaml"):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        opening = (data or {}).get("opening") or {}
        says = opening.get("npc_says")
        if isinstance(says, str) and says:
            lines.append(says)
    assert len(lines) >= 25, "expected the tutorial script plus every pack opening"
    return lines


class TestExtractor:
    def test_decodes_a_plain_line_in_one_chunk(self):
        ex = UtteranceStreamExtractor()
        out = ex.feed('{"npc_utterance": "Hello there. I am here.", "npc_emotion": "warm"}')
        assert out == "Hello there. I am here."
        assert ex.done and not ex.abandoned
        # Nothing after the closing quote is ever decoded.
        assert ex.feed(', "state_delta": {}}') == ""

    def test_decodes_simple_escapes(self):
        ex = UtteranceStreamExtractor()
        out = ex.feed(json.dumps({"npc_utterance": 'She said "no".\nThen left.\tBack\\slash'}))
        assert out == 'She said "no".\nThen left.\tBack\\slash'

    def test_decodes_unicode_escapes_and_surrogate_pairs(self):
        line = "Café ☕ — 🤔 fin"
        encoded = json.dumps({"npc_utterance": line}, ensure_ascii=True)
        assert "\\ud83e" in encoded  # the emoji travels as a surrogate pair
        ex = UtteranceStreamExtractor()
        assert ex.feed(encoded) == line

    def test_a_lone_surrogate_becomes_the_replacement_character(self):
        ex = UtteranceStreamExtractor()
        out = ex.feed('{"npc_utterance": "a\\ud83eb"}')
        assert out == "a�b"
        ex = UtteranceStreamExtractor()
        assert ex.feed('{"npc_utterance": "a\\ude00b"}') == "a�b"

    def test_gives_up_when_another_key_comes_first(self):
        ex = UtteranceStreamExtractor()
        assert ex.feed('{"npc_emotion": "warm", "npc_utterance": "Hi"}') == ""
        assert ex.abandoned and not ex.done

    def test_gives_up_on_prose(self):
        ex = UtteranceStreamExtractor()
        assert ex.feed("Sure! Here is the JSON you asked for: {") == ""
        assert ex.abandoned

    def test_tolerates_whitespace_and_newlines_before_the_key(self):
        ex = UtteranceStreamExtractor()
        assert ex.feed('\n  {\n    "npc_utterance" :\n "Hi there."') == "Hi there."

    def test_partial_key_across_chunks(self):
        ex = UtteranceStreamExtractor()
        assert ex.feed('{"npc_utt') == ""
        assert ex.feed('erance": "Yes') == "Yes"
        assert ex.feed('."}') == "."
        assert ex.done

    @pytest.mark.parametrize("ensure_ascii", [True, False])
    def test_round_trips_every_spoken_line_split_at_every_offset(self, ensure_ascii):
        for line in _all_spoken_lines():
            encoded = json.dumps(
                {"npc_utterance": line, "npc_emotion": "neutral"}, ensure_ascii=ensure_ascii
            )
            for split_at in range(len(encoded) + 1):
                out, done = _decode_all(encoded, split_at)
                assert out == line, (line, split_at)
                assert done

    def test_round_trips_under_random_multi_chunking(self):
        rng = random.Random(538)
        for line in _all_spoken_lines():
            encoded = json.dumps({"npc_utterance": line, "npc_emotion": "neutral"}, ensure_ascii=True)
            for _ in range(5):
                ex = UtteranceStreamExtractor()
                pos = 0
                out = ""
                while pos < len(encoded):
                    step = rng.randint(1, 7)
                    out += ex.feed(encoded[pos : pos + step])
                    pos += step
                assert out == line
                assert ex.done

    def test_text_property_accumulates(self):
        ex = UtteranceStreamExtractor()
        ex.feed('{"npc_utterance": "One. ')
        ex.feed('Two."}')
        assert ex.text == "One. Two."


def _safe(_: str) -> OutputValidationResult:
    return OutputValidationResult()


def _unsafe_when(marker: str):
    def check(text: str) -> OutputValidationResult:
        if marker in text:
            return OutputValidationResult(
                violations=[OutputViolation(category="test", reason="marker", is_recoverable=True)]
            )
        return OutputValidationResult()

    return check


class TestSentenceGate:
    def test_releases_complete_sentences_and_holds_the_tail(self):
        gate = SentenceGate(checker=_safe)
        assert gate.feed("First one. Second", done=False) == ["First one."]
        assert gate.feed("First one. Second one! Third", done=False) == [" Second one!"]
        assert gate.feed("First one. Second one! Third.", done=True) == [" Third."]
        assert gate.released_text == "First one. Second one! Third."

    def test_a_trailing_boundary_waits_for_more_text_or_the_close(self):
        gate = SentenceGate(checker=_safe)
        # "Mr." could be an abbreviation; the gate holds a boundary at the very end.
        assert gate.feed("Hello.", done=False) == []
        assert gate.feed("Hello.", done=True) == ["Hello."]

    def test_released_slices_concatenate_to_the_line_exactly(self):
        line = "Well... I see. Do you?  Yes! Fine.\n"
        gate = SentenceGate(checker=_safe)
        out: list[str] = []
        for i in range(1, len(line) + 1):
            out += gate.feed(line[:i], done=(i == len(line)))
        assert "".join(out) == line

    def test_a_failing_sentence_blocks_everything_after_it(self):
        gate = SentenceGate(checker=_unsafe_when("BAD"))
        assert gate.feed("Fine one. Also fine. BAD here. More.", done=True) == ["Fine one.", " Also fine."]
        assert gate.blocked is not None and gate.blocked.first_violation.category == "test"
        assert gate.feed("Fine one. Also fine. BAD here. More. Even more.", done=True) == []
        assert gate.released_text == "Fine one. Also fine."

    def test_nothing_is_released_when_the_first_sentence_fails(self):
        gate = SentenceGate(checker=_unsafe_when("BAD"))
        assert gate.feed("BAD start. Fine.", done=True) == []
        assert gate.blocked is not None
        assert gate.released_text == ""

    def test_uses_the_real_output_check_by_default(self):
        gate = SentenceGate(hidden_agenda=None)
        assert gate.feed("I'd love to hear more. Tell me about it.", done=True) == [
            "I'd love to hear more.",
            " Tell me about it.",
        ]
        leaky = SentenceGate(hidden_agenda=None)
        leaky.feed("Nice to meet you. My hidden agenda is to stall you.", done=True)
        assert leaky.released_text == "Nice to meet you."
        assert leaky.blocked is not None
