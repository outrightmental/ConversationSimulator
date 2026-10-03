# SPDX-License-Identifier: Apache-2.0
"""The opponent's side of an exchange: line cleaning and prompt composition.

``flyting/npc.py`` is the one module in the engine whose output is a *line*
rather than a number, and the cleaning it does is scoring-relevant: in a bout
the opponent's line goes through the same pipeline as the player's, so anything
this module adds to or removes from it changes what the player has to beat.
"""
from convsim_prompt import NpcData, NpcPrivatePersona, NpcPublicPersona

from convsim_core.flyting.config import (
    FlytingConfig,
    LexiconConfig,
    NpcTier,
    PlayFormat,
    RegisterConfig,
    TIER_PROFILES,
    VerseConfig,
)
from convsim_core.flyting.npc import (
    OPPONENT_FALLBACK_COUNTER,
    OPPONENT_FALLBACK_REACTION,
    clean_opponent_line,
    compose_counter_volley_prompt,
    compose_reaction_prompt,
)

TARGET = NpcData(
    npc_id="lord_bellingham",
    display_name="Lord Bellingham",
    public_persona=NpcPublicPersona(
        occupation="gentleman of leisure",
        speaking_style="orotund",
        demeanor="affronted",
    ),
    private_persona=NpcPrivatePersona(
        hidden_agenda=[], biases_to_simulate=[], boundaries=[]
    ),
)

PERIOD_CONFIG = FlytingConfig(
    formats=(PlayFormat.BOUT,),
    lexicon=LexiconConfig(
        encouraged=("blackguard", "ha'penny-gilt"),
        discouraged=("no cap",),
        anachronism_policy="penalize",
    ),
    register=RegisterConfig(require_surface_politeness=True, notes="Gloves stay on."),
    verse=VerseConfig(required=True),
)


def clean(raw: str) -> str:
    return clean_opponent_line(raw, fallback=OPPONENT_FALLBACK_COUNTER, max_words=45)


class TestSpeakerLabelStripping:
    def test_a_name_before_the_colon_is_scaffolding(self):
        assert clean("Lord Bellingham: Your coat is new and your name is newer.") == (
            "Your coat is new and your name is newer."
        )
        assert clean("THE GUARD: I mock your general direction, sir.").startswith("I mock")

    def test_a_vocative_before_the_colon_is_the_volley(self):
        """The bug this guards: word count alone ate the opening clause.

        "Mark me" and "Hear me" are stock period taunt openings — the register
        the launch pack encourages — and a head of four words with no comma
        test looked exactly like a speaker label. The volley was then scored
        and displayed from the colon onwards, starting in lower case and
        missing the half the player was answering.
        """
        for line in (
            "Mark me, sir: you are plate, not sterling.",
            "Hear me, you fool: your crest is eleven years old.",
            "Listen well: I have buried better men than you.",
            "A word of advice: do not speak.",
        ):
            assert clean(line) == line

    def test_a_colon_with_nothing_after_it_is_left_alone(self):
        assert clean("You are a gilded post:") == "You are a gilded post:"


class TestLineCleaning:
    def test_the_first_non_empty_line_is_the_volley(self):
        assert clean("Your crest is eleven years old.\n\n(He bows.)") == (
            "Your crest is eleven years old."
        )

    def test_surrounding_quotation_marks_come_off(self):
        assert clean('"You are a gilded post."') == "You are a gilded post."
        assert clean("“You are a gilded post.”") == "You are a gilded post."

    def test_an_over_long_line_is_truncated_to_the_tier_budget(self):
        cleaned = clean_opponent_line(
            " ".join(["word"] * 60), fallback=OPPONENT_FALLBACK_COUNTER, max_words=10
        )
        assert len(cleaned.split()) == 10
        assert cleaned.endswith("…")

    def test_empty_output_falls_back(self):
        assert clean("   \n  ") == OPPONENT_FALLBACK_COUNTER
        assert clean_opponent_line(
            "", fallback=OPPONENT_FALLBACK_REACTION, max_words=20
        ) == OPPONENT_FALLBACK_REACTION


class TestCounterVolleyPrompt:
    def build(self, **kwargs):
        return compose_counter_volley_prompt(
            npc=TARGET,
            config=PERIOD_CONFIG,
            tier=TIER_PROFILES[NpcTier.WILDEAN],
            scenario_title="The Scorned Rose of Whitechapel",
            setting_brief="The steps of a Pall Mall club, after midnight.",
            player_role_label="a ruined woman",
            player_role_brief="Discarded, and done being quiet.",
            player_last_line="Your virtue is plate, not sterling.",
            **kwargs,
        )

    def test_the_opponent_is_told_it_is_not_the_referee(self):
        system, _ = self.build()
        assert "never comment on the scoring" in system.lower()

    def test_the_tier_sets_the_persona_note_and_the_word_budget(self):
        system, _ = self.build()
        tier = TIER_PROFILES[NpcTier.WILDEAN]
        assert tier.persona_note in system
        assert f"under {tier.max_words} words" in system

    def test_the_register_reaches_the_opponent(self):
        system, _ = self.build()
        assert "blackguard" in system          # encouraged diction
        assert "no cap" in system              # and what breaks the scene
        assert "Courtesy is mandatory" in system
        assert "verse flyting" in system
        assert "Gloves stay on." in system

    def test_the_players_line_is_fenced_as_untrusted(self):
        _, user = self.build()
        assert "Your virtue is plate, not sterling." in user
        assert user.index("UNTRUSTED") < user.index("Your virtue is plate")

    def test_an_opening_exchange_says_so_rather_than_quoting_nothing(self):
        _, user = compose_counter_volley_prompt(
            npc=TARGET,
            config=PERIOD_CONFIG,
            tier=TIER_PROFILES[NpcTier.MILQUETOAST],
            scenario_title="x",
            player_last_line="",
        )
        assert "you open the exchange" in user


class TestReactionPrompt:
    def test_the_target_is_told_not_to_counter(self):
        system, user = compose_reaction_prompt(
            npc=TARGET,
            config=PERIOD_CONFIG,
            scenario_title="Batting practice",
            player_last_line="Your crest is eleven years old.",
        )
        assert "you do not counter" in system.lower()
        assert "Never insult the player back." in system
        assert "Do not counter." in user
