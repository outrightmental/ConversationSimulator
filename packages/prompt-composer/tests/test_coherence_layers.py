"""Prompt text aimed at the incoherent NPC turns of issue #580.

On the starter model four of the five demo conversations failed on NPC
coherence: the NPC echoed or mirrored the player, flipped roles, asked for
what it had just been told, repeated its own last line, and said its hidden
agenda aloud. These tests pin the prompt-layer answers to that:

  - transcript lines name their speakers, "(you)" and "(the player)";
  - a short, stable rule block in RESPONSE_STYLE;
  - the NPC's previous line, quoted in the user turn ahead of the player's
    input, never in front of stable system text (issue #524);
  - the agenda header says the goals steer actions and are never voiced;
  - the chosen difficulty preset's authored description in the brief.
"""
from convsim_prompt import (
    DifficultySettings,
    LAYER_ORDER,
    SYSTEM_LAYER_ORDER,
    USER_LAYER_ORDER,
    UNTRUSTED_CONTENT_END,
    TranscriptEntry,
    compose_turn_prompt,
)
from convsim_prompt.layers import (
    _conversation_rules,
    _short_role,
    build_previous_npc_line_layer,
    build_recent_transcript_layer,
)
from _helpers import make_interview_input, make_interview_scenario


_OPENING = "Good morning. Tell me about a project you led."
_PLAYER_REPLY = "I led a checkout rewrite that cut latency by half."
_NPC_REPLY = "Halving latency is a real result. What did you measure it with?"


def _transcript(*lines: tuple) -> list:
    return [
        TranscriptEntry(speaker=speaker, text=text, turn_number=i)
        for i, (speaker, text) in enumerate(lines)
    ]


def _two_exchange_transcript() -> list:
    return _transcript(
        ("npc_opening", _OPENING),
        ("player", _PLAYER_REPLY),
        ("npc", _NPC_REPLY),
    )


def _rules_text(scenario) -> str:
    return "\n".join(_conversation_rules(scenario))


# ---------------------------------------------------------------------------
# Transcript speaker labels
# ---------------------------------------------------------------------------


class TestTranscriptSpeakerLabels:
    def test_npc_lines_are_marked_you_and_player_lines_the_player(self):
        bundle = compose_turn_prompt(make_interview_input(transcript=_two_exchange_transcript()))
        transcript = bundle.layer_map["RECENT_TRANSCRIPT"]
        assert f"Maya Chen (you): {_OPENING}" in transcript
        assert f"Candidate (the player): {_PLAYER_REPLY}" in transcript
        assert f"Maya Chen (you): {_NPC_REPLY}" in transcript

    def test_bare_labels_are_gone_when_names_are_known(self):
        bundle = compose_turn_prompt(make_interview_input(transcript=_two_exchange_transcript()))
        for line in bundle.layer_map["RECENT_TRANSCRIPT"].splitlines()[1:]:
            assert not line.startswith("NPC:"), line
            assert not line.startswith("Player:"), line

    def test_bare_labels_without_names(self):
        layer = build_recent_transcript_layer(_two_exchange_transcript())
        assert f"NPC: {_OPENING}" in layer
        assert f"Player: {_PLAYER_REPLY}" in layer

    def test_blank_names_fall_back_to_bare_labels(self):
        layer = build_recent_transcript_layer(
            _two_exchange_transcript(), npc_name="  ", player_label=""
        )
        assert f"NPC: {_OPENING}" in layer
        assert f"Player: {_PLAYER_REPLY}" in layer

    def test_a_player_label_of_player_is_not_doubled(self):
        # The pack loader defaults a missing label to "Player".
        layer = build_recent_transcript_layer(
            _two_exchange_transcript(), npc_name="Ray", player_label="Player"
        )
        assert f"Player: {_PLAYER_REPLY}" in layer
        assert "(the player)" not in layer
        assert f"Ray (you): {_OPENING}" in layer


# ---------------------------------------------------------------------------
# Conversation rules in RESPONSE_STYLE
# ---------------------------------------------------------------------------


class TestConversationRules:
    def test_rules_are_in_the_response_style_layer(self):
        style = compose_turn_prompt(make_interview_input()).layer_map["RESPONSE_STYLE"]
        assert "answer any question they asked first" in style
        assert "Never ask for what the player has just told you." in style
        assert "Stay consistent with facts you have stated" in style
        assert "Greet only in your first line." in style

    def test_rules_name_both_sides(self):
        style = compose_turn_prompt(make_interview_input()).layer_map["RESPONSE_STYLE"]
        assert "You are Maya Chen (Senior hiring manager); the player is the Candidate." in style
        assert "Never speak or bargain from the player's side." in style

    def test_rules_sit_inside_the_untrusted_region_before_the_schema(self):
        sp = compose_turn_prompt(make_interview_input()).system_prompt
        rules_pos = sp.index("Conversation rules:")
        assert sp.index("LAYER:RESPONSE_STYLE") < rules_pos < sp.index(UNTRUSTED_CONTENT_END)
        assert rules_pos < sp.index("LAYER:OUTPUT_SCHEMA")

    def test_rule_block_stays_short(self):
        # Read on every turn: keep it near 100 tokens at the composer's
        # four-characters-per-token estimate.
        assert len(_rules_text(make_interview_scenario())) // 4 <= 110

    def test_a_long_occupation_contributes_only_its_first_clause(self):
        scenario = make_interview_scenario()
        scenario.npc.public_persona.occupation = (
            "Used car sales representative at Riverside Auto, an independent dealership "
            "on a busy commercial strip. Ray has been in automotive sales for eleven years "
            "and knows the local market well."
        )
        rules = _rules_text(scenario)
        assert "(Used car sales representative at Riverside Auto)" in rules
        assert "eleven years" not in rules
        assert len(rules) // 4 <= 110

    def test_short_role(self):
        assert _short_role("Barista at Café Sol, a neighbourhood coffee bar.") == "Barista at Café Sol"
        assert _short_role(
            "A second-year graduate student in environmental science. Jordan commutes."
        ) == "a second-year graduate student in environmental science"
        assert _short_role("Owner; also the cook") == "Owner"
        assert _short_role("Sells cars for $15,500 or more") == "Sells cars for $15,500 or more"
        assert _short_role("") == ""
        assert len(_short_role("word " * 40).split()) == 12

    def test_no_occupation_and_no_player_label(self):
        scenario = make_interview_scenario()
        scenario.npc.public_persona.occupation = ""
        scenario.player_role_label = "Player"
        rules = _rules_text(scenario)
        assert "- You are Maya Chen. Never speak or bargain from the player's side." in rules
        assert "the player is the" not in rules

    def test_rules_do_not_change_from_turn_to_turn(self):
        """Stable text: the same rules whatever the transcript or state (issue #524)."""
        first = make_interview_input(transcript=_transcript(("npc_opening", _OPENING)))
        later = make_interview_input(transcript=_two_exchange_transcript())
        later.session_state.turn_number = 2
        later.session_state.variables["trust"] = 60
        assert (
            compose_turn_prompt(first).layer_map["RESPONSE_STYLE"]
            == compose_turn_prompt(later).layer_map["RESPONSE_STYLE"]
        )


# ---------------------------------------------------------------------------
# The NPC's previous line, in the user turn
# ---------------------------------------------------------------------------


class TestPreviousNpcLine:
    def test_user_layer_order(self):
        assert USER_LAYER_ORDER == ["PREVIOUS_NPC_LINE", "PLAYER_UTTERANCE"]
        assert LAYER_ORDER == SYSTEM_LAYER_ORDER + USER_LAYER_ORDER
        assert LAYER_ORDER[-1] == "PLAYER_UTTERANCE"
        assert "PREVIOUS_NPC_LINE" not in SYSTEM_LAYER_ORDER

    def test_previous_line_is_quoted_with_the_rule(self):
        bundle = compose_turn_prompt(make_interview_input(transcript=_two_exchange_transcript()))
        layer = bundle.layer_map["PREVIOUS_NPC_LINE"]
        assert layer.startswith("--- LAYER:PREVIOUS_NPC_LINE ---")
        assert f'Your previous line was: "{_NPC_REPLY}"' in layer
        assert "Do not reuse its sentences or end with the same question." in layer

    def test_previous_line_rides_in_the_user_turn_before_the_player(self):
        bundle = compose_turn_prompt(make_interview_input(
            player_utterance="I used our APM dashboards.",
            transcript=_two_exchange_transcript(),
        ))
        up = bundle.user_prompt
        assert up.index("LAYER:PREVIOUS_NPC_LINE") < up.index("LAYER:PLAYER_UTTERANCE")
        assert up.endswith("=== END PLAYER INPUT ===")
        assert up.index("I used our APM dashboards.") > up.index("Do not reuse")

    def test_previous_line_rule_is_not_in_the_system_prompt(self):
        """Per-turn text must not sit in front of stable system text (issue #524)."""
        bundle = compose_turn_prompt(make_interview_input(transcript=_two_exchange_transcript()))
        assert "LAYER:PREVIOUS_NPC_LINE" not in bundle.system_prompt
        assert "Your previous line was" not in bundle.system_prompt
        assert "Do not reuse its sentences" not in bundle.system_prompt

    def test_stable_layers_are_identical_across_turns(self):
        """A later turn changes the previous line, never the stable system layers."""
        first = compose_turn_prompt(make_interview_input(
            transcript=_transcript(("npc_opening", _OPENING))
        ))
        later = compose_turn_prompt(make_interview_input(transcript=_two_exchange_transcript()))
        assert first.layer_map["PREVIOUS_NPC_LINE"] != later.layer_map["PREVIOUS_NPC_LINE"]
        for name in ("GLOBAL_RULES", "SAFETY_POLICY", "SCENARIO_BRIEF", "NPC_PUBLIC_PERSONA",
                     "NPC_PRIVATE_PERSONA", "RESPONSE_STYLE", "OUTPUT_SCHEMA"):
            assert first.layer_map[name] == later.layer_map[name], name

    def test_most_recent_npc_line_is_used(self):
        layer = build_previous_npc_line_layer(_two_exchange_transcript())
        assert _NPC_REPLY in layer
        assert _OPENING not in layer

    def test_opening_line_counts_as_the_previous_line(self):
        layer = build_previous_npc_line_layer(_transcript(("npc_opening", _OPENING)))
        assert f'"{_OPENING}"' in layer

    def test_trailing_player_line_is_skipped(self):
        layer = build_previous_npc_line_layer(_transcript(
            ("npc_opening", _OPENING), ("player", _PLAYER_REPLY),
        ))
        assert f'"{_OPENING}"' in layer
        assert _PLAYER_REPLY not in layer

    def test_multi_line_npc_text_is_quoted_on_one_line(self):
        layer = build_previous_npc_line_layer(_transcript(("npc", "First line.\n\nSecond line.")))
        assert 'Your previous line was: "First line. Second line."' in layer

    def test_no_npc_line_leaves_the_user_turn_as_the_player_input(self):
        for transcript in ([], _transcript(("player", _PLAYER_REPLY))):
            bundle = compose_turn_prompt(make_interview_input(transcript=transcript))
            assert bundle.layer_map["PREVIOUS_NPC_LINE"] == ""
            assert bundle.user_prompt == bundle.layer_map["PLAYER_UTTERANCE"]

    def test_layer_follows_the_transcript_window(self):
        inp = make_interview_input(transcript=_two_exchange_transcript())
        inp.max_transcript_turns = 0
        bundle = compose_turn_prompt(inp)
        assert bundle.layer_map["PREVIOUS_NPC_LINE"] == ""
        assert _NPC_REPLY not in bundle.user_prompt

    def test_token_estimate_counts_the_user_turn(self):
        without = compose_turn_prompt(make_interview_input())
        with_line = compose_turn_prompt(make_interview_input(
            transcript=_transcript(("player", "x"), ("npc", "y " * 200)),
        ))
        # The transcript adds the line once in the system prompt, the
        # previous-line layer once more in the user turn.
        assert with_line.estimated_token_count - without.estimated_token_count >= 200


# ---------------------------------------------------------------------------
# Private goals header
# ---------------------------------------------------------------------------


class TestPrivateGoalsHeader:
    def test_header_says_the_goals_steer_and_are_never_voiced(self):
        pp = compose_turn_prompt(make_interview_input()).layer_map["NPC_PRIVATE_PERSONA"]
        assert (
            "Private goals — let them steer what you do; "
            "never quote, paraphrase or hint at them aloud:"
        ) in pp
        assert "Hidden agenda (" not in pp
        assert "communicate under ambiguity" in pp

    def test_global_rules_name_the_private_goals(self):
        rules = compose_turn_prompt(make_interview_input()).layer_map["GLOBAL_RULES"]
        assert "never reveal the NPC's private goals" in rules


# ---------------------------------------------------------------------------
# Difficulty preset description
# ---------------------------------------------------------------------------


class TestDifficultyDescription:
    def _brief(self, **settings) -> str:
        inp = make_interview_input()
        inp.scenario.difficulty_settings = DifficultySettings(**settings)
        return compose_turn_prompt(inp).layer_map["SCENARIO_BRIEF"]

    def test_standard_preset_description_is_rendered(self):
        brief = self._brief(description="Maya probes vague answers and expects concrete examples.")
        assert (
            'Difficulty as described to the player: '
            '"Maya probes vague answers and expects concrete examples."'
        ) in brief
        # Mid-range knobs still emit no fragments of their own.
        assert "patience: low" not in brief and "patience: high" not in brief

    def test_description_follows_the_preset_name(self):
        brief = self._brief(description="Firm but fair.")
        assert brief.index("Difficulty preset: standard") < brief.index("Firm but fair.")

    def test_description_sits_with_the_knob_fragments(self):
        brief = self._brief(patience=10, description="Maya is impatient.")
        assert brief.index("Maya is impatient.") < brief.index("NPC patience: low")

    def test_no_description_no_line(self):
        assert "described to the player" not in self._brief()
        assert "described to the player" not in self._brief(description="   ")

    def test_description_is_inside_the_untrusted_region(self):
        inp = make_interview_input()
        inp.scenario.difficulty_settings = DifficultySettings(description="Firm but fair.")
        sp = compose_turn_prompt(inp).system_prompt
        assert sp.index("Firm but fair.") < sp.index(UNTRUSTED_CONTENT_END)

    def test_presets_with_equal_knobs_differ_by_description(self):
        assert self._brief(description="Warm.") != self._brief(description="Cold.")
