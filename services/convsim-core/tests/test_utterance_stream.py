# SPDX-License-Identifier: Apache-2.0
"""The spoken line is decoded from the model's JSON as it arrives (#538)."""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest
import yaml

from convsim_core.runtime import scripted
from convsim_core.services.utterance_stream import (
    SentenceGate,
    UtteranceStreamExtractor,
    first_sentence_repeats,
)
from convsim_prompt.output_validator import OutputValidationResult, OutputViolation
from convsim_prompt.repetition import RepetitionReport

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


# ---------------------------------------------------------------------------
# The gate holds back a repeating first sentence (issue #580)
# ---------------------------------------------------------------------------

_RAY_T3 = (
    "That's a solid offer, and I see your point. Let me check if we can make it work. "
    "What's the smallest you'd be open to for the car?"
)
# Verbatim from the issue #580 transcripts: what each NPC said before, and the
# line that repeated it.
_DANA_OPENING = (
    "Good morning! Thanks so much for making the time. I'm Dana Reyes, Engineering "
    "Manager on the platform team here at Meridian Systems. I've looked over your "
    "resume — very interesting background. To kick things off, tell me about a time "
    "when you had to work through a difficult technical problem under real pressure. "
    "What was the situation, and how did you handle it?"
)
_RAY_T2_ISSUE = (
    "I see what you're saying. The car is priced at $15,500, but I understand your "
    "perspective. Let me check the tire situation — we do have new tires on hand. "
    "What's the lowest you'd be willing to go?"
)
_RAY_T3_ISSUE = (
    "That's a solid offer, and I see your point. Let me check if we can make it work. "
    "We do have new tires on hand, so that could be a nice addition. "
    "What's the smallest you'd be open to for the car?"
)
_RAY_T4_ISSUE = (
    "I understand your offer. Let me check if we can make this work. "
    "We do have new tires on hand, so that’s a good match. "
    "What’s the smallest you’d be open to for the car?"
)
_DIANE_T1 = (
    "You mentioned leading a cross-team migration, onboarding two new hires, and "
    "shipping three weeks early. Can you quantify the impact of these achievements on "
    "our company's bottom line? What specific metrics or outcomes have you observed?"
)
_DIANE_T2 = (
    "I see the market rate. But without specific data on the cost to the company of not "
    "giving you the raise, I can't justify this request. What's the financial impact of "
    "not adjusting your compensation?"
)
_DIANE_T3 = (
    "I see. Let's focus on what we can address this cycle. What specific metrics or "
    "outcomes have you observed that would justify a partial adjustment now?"
)


def _stream(gate: SentenceGate, line: str) -> list[str]:
    """Feed ``line`` one character at a time, as tokens would arrive."""
    out: list[str] = []
    for i in range(1, len(line) + 1):
        out += gate.feed(line[:i], done=(i == len(line)))
    return out


class TestSentenceGateRepetition:
    def test_a_first_sentence_that_repeats_holds_back_the_whole_line(self):
        gate = SentenceGate(checker=_safe, previous_lines=[_RAY_T3])
        assert _stream(gate, "That's a solid offer, and I see your point. Here is my number.") == []
        assert gate.released_text == ""
        assert gate.repeated is not None and gate.repeated.longest_run == 9
        # Not a safety block: the pipeline keeps the stream running.
        assert gate.blocked is None
        # Nothing is ever released after it, so the guard can replace the line.
        assert gate.feed("That's a solid offer, and I see your point. Here is my number.", done=True) == []

    @pytest.mark.parametrize("previous, line", [
        # Dana's follow-up shares the stock 7-word "tell me about a time when
        # you" with her opening. Cut there, the line had no question at all.
        ([_DANA_OPENING], (
            "An N+1 query behind holiday timeouts, fixed overnight. Tell me about a time "
            "when you made a mistake that affected your team. What did you learn from it?"
        )),
        # Ray's answer to the walk-away ultimatum, and the turn before it.
        ([_RAY_T3_ISSUE], _RAY_T4_ISSUE),
        ([_RAY_T2_ISSUE], _RAY_T3_ISSUE),
        # Diane's T1 question, two lines back.
        ([_DIANE_T2, _DIANE_T1], _DIANE_T3),
        # A run that starts in the first sentence and ends in the second.
        (["Okay, sure. Let me check with my manager about the price."],
         "Okay, sure. Let me check with my manager on that."),
        # The previous line's closing question, after a new first sentence.
        (["That's our best price. Does that work for you?"], "I can add floor mats. Does that work for you?"),
    ])
    def test_a_repeat_after_the_first_sentence_streams_with_the_line(self, previous, line):
        """Holding a later sentence back cannot undo what is on screen, only
        cut the line short; the pipeline notes the repeat after the line."""
        gate = SentenceGate(checker=_safe, previous_lines=previous)
        out = _stream(gate, line)
        assert "".join(out) == gate.released_text == line
        assert len(out) >= 2
        assert gate.repeated is None
        from convsim_prompt.repetition import check_repetition

        assert check_repetition(line, previous).flagged

    def test_sentences_arriving_together_are_judged_as_one_first_release(self):
        gate = SentenceGate(checker=_safe, previous_lines=[_RAY_T3])
        line = "I hear you. What's the smallest you'd be open to for the car?"
        assert gate.feed(line, done=True) == ["I hear you.", " What's the smallest you'd be open to for the car?"]
        assert gate.repeated is None

    def test_the_line_before_the_previous_one_counts(self):
        older = "What specific metrics or outcomes have you observed from your work?"
        gate = SentenceGate(checker=_safe, previous_lines=["Where does that number come from?", older])
        assert _stream(gate, "What specific metrics or outcomes have you observed lately? Tell me.") == []
        assert gate.repeated.against == (1,)

    def test_a_first_sentence_ending_on_the_previous_closing_question_is_held(self):
        """Any released prefix can become the committed line (a later sentence
        may fail the safety check), so a first release that ends with the
        previous line's closing question is never let out."""
        previous = "That's our best price. Does that work for you?"
        gate = SentenceGate(checker=_safe, previous_lines=[previous])
        assert _stream(gate, "Does that work for you? I can also add mats.") == []
        assert [m.kind for m in gate.repeated.matches] == ["question"]

    def test_later_sentences_are_still_checked_for_safety(self):
        gate = SentenceGate(checker=_unsafe_when("BAD"), previous_lines=[_RAY_T3])
        out = _stream(gate, "I hear you. What's the smallest you'd be open to for the car? BAD words now.")
        assert out == ["I hear you.", " What's the smallest you'd be open to for the car?"]
        assert gate.blocked is not None
        assert gate.repeated is None

    def test_whole_line_similarity_holds_a_line_nothing_of_which_is_out(self):
        # One sentence: nothing is released before the line is done. Its two
        # clauses swapped share no 6-word run, only trigrams.
        previous = "The brakes are all fresh, we put new tires on."
        line = "We put new tires on, the brakes are all fresh."
        gate = SentenceGate(checker=_safe, previous_lines=[previous])
        assert _stream(gate, line) == []
        assert [m.kind for m in gate.repeated.matches] == ["similar"]

    def test_similarity_does_not_shorten_a_line_already_on_screen(self):
        previous = "We have new tires. The brakes are fresh too."
        line = "The brakes are fresh too. We have new tires."
        from convsim_prompt.repetition import check_repetition

        assert [m.kind for m in check_repetition(line, [previous]).matches] == ["similar"]
        gate = SentenceGate(checker=_safe, previous_lines=[previous])
        assert _stream(gate, line) == ["The brakes are fresh too.", " We have new tires."]
        assert gate.repeated is None

    @pytest.mark.parametrize("previous, line", [
        ("Great, thanks for sharing that with me.", "Great, thanks for sharing that."),
        ("Son cuatro euros con cincuenta, por favor.", "Son cuatro euros con cincuenta."),
    ])
    def test_a_short_line_is_not_held_for_similarity(self, previous, line):
        gate = SentenceGate(checker=_safe, previous_lines=[previous])
        assert _stream(gate, line) == [line]
        assert gate.repeated is None

    def test_a_fresh_line_streams_as_before(self):
        line = "Twelve-five is fair. Can you sign today?"
        with_history = SentenceGate(checker=_safe, previous_lines=[_RAY_T3, "Welcome in."])
        without = SentenceGate(checker=_safe)
        assert _stream(with_history, line) == _stream(without, line) == ["Twelve-five is fair.", " Can you sign today?"]
        assert with_history.repeated is None

    def test_a_safety_failure_is_checked_first(self):
        gate = SentenceGate(checker=_unsafe_when("BAD"), previous_lines=["BAD words here, said once before today."])
        gate.feed("BAD words here, said once before today. Okay.", done=True)
        assert gate.blocked is not None
        assert gate.repeated is None

    def test_a_broken_repetition_check_never_holds_a_sentence(self, monkeypatch):
        from convsim_core.services import utterance_stream

        def boom(*_a, **_k):
            raise RuntimeError("broken")

        monkeypatch.setattr(utterance_stream, "check_repetition", boom)
        gate = SentenceGate(checker=_safe, previous_lines=[_RAY_T3])
        assert gate.feed(_RAY_T3, done=True) != []
        assert gate.released_text == _RAY_T3
        assert gate.repeated is None


class TestFirstSentenceRepeats:
    """The gate's judgement of a complete line, which the guard judges a held line's retry by."""

    @pytest.mark.parametrize("previous, line", [
        (["Good to hear it. What brings you here?"], "What brings you here? Twelve is close and I can work with it."),
        ([_RAY_T3], "That's a solid offer, and I see your point. Here is my number."),
        (["The brakes are all fresh, we put new tires on."], "We put new tires on, the brakes are all fresh."),
        ([_RAY_T3], "I hear you. What's the smallest you'd be open to for the car?"),
        (["That's our best price. Does that work for you?"], "I can add floor mats. Does that work for you?"),
        ([_RAY_T3, "Welcome in."], "Twelve-five is fair. Can you sign today?"),
    ])
    def test_it_agrees_with_the_streamed_gate(self, previous, line):
        gate = SentenceGate(checker=_safe, previous_lines=previous)
        _stream(gate, line)
        assert first_sentence_repeats(line, previous) == (gate.repeated or RepetitionReport())

    def test_a_line_opening_with_the_previous_question_is_held_for_it(self):
        report = first_sentence_repeats(
            "What brings you here? Twelve is close and I can work with it.",
            ["Good to hear it. What brings you here?"],
        )
        assert [(m.kind, m.words) for m in report.matches] == [("question", ("what", "brings", "you", "here"))]

    def test_it_runs_no_output_check(self):
        # The guard has already checked the whole line; a sentence the output
        # check would block is still judged for repetition.
        previous = ["Okay. My hidden agenda is to keep you talking?"]
        report = first_sentence_repeats("My hidden agenda is to keep you talking? Sure.", previous)
        assert report.flagged
