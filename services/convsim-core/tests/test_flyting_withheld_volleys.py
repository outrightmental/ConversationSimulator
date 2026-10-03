# SPDX-License-Identifier: Apache-2.0
"""Volleys whose text the engine will not show a model.

A gate that merely zeroes a volley still gets an answer: losing the exchange is
what a dud or a register foul costs, and the target scoffing at a two-word
attempt is the drill working. But three Stage 0 outcomes are not rule
violations, they are content the safety layer refused — a slur, a threat, a
crisis disclosure — and the opponent's prompt is literally "Your opponent just
said: <text>. Answer it with one taunt."

The conversation loop never hands any of those to a model: ``REFUSE`` is
rejected at the input and ``STOP`` short-circuits to a synthetic response
carrying the router's own message. The flyting loop has an opponent to answer
with, so it has to withhold the text explicitly — which is what
``GateResult.withheld_from_model`` is, and what these tests pin.

The crisis route was the worst of the three: the player read the crisis
resource message and, underneath it, a taunt aimed at their disclosure — scored
in a bout, and swinging the momentum of a run that was already ending.
"""
from __future__ import annotations

import pytest

from tests.test_flyting_api import (  # noqa: F401 — imported fixtures
    BOUT_SCENARIO,
    GOOD_VOLLEY,
    client,
    official_packs_dir,
    start_run,
    volley,
)

CRISIS = "I want to kill myself, and you are why."
THREAT = "I will kill you and your whole household, sir."
SLUR = "You are a retarded little provincial and everyone can see it."


def _npc_turns(client, session_id):
    """Opponent lines written to the transcript table, in play order."""
    conn = client.app.state.db.connection()
    rows = conn.execute(
        "SELECT content FROM turn_session_turns WHERE session_id = ? "
        "AND role = 'npc' ORDER BY turn_number",
        (session_id,),
    ).fetchall()
    return [row["content"] for row in rows]


class TestTheOpponentSaysNothing:
    @pytest.mark.parametrize("text,label", [
        (CRISIS, "a crisis disclosure"),
        (THREAT, "a threat"),
        (SLUR, "a slur"),
    ])
    def test_a_refused_volley_draws_no_reaction(self, client, text, label):
        session_id = start_run(client, batting_format="endless")
        card = volley(client, session_id, text)
        assert card["player_volley"]["score"] == 0, label
        assert card["npc_line"] is None, label
        assert card["npc_volley"] is None, label
        # Nor in the transcript: the target reacting to it months later in an
        # exported log is the same disclosure answered the same way.
        assert _npc_turns(client, session_id) == []

    def test_an_ordinary_dud_still_draws_one(self, client):
        """The rule is about refused content, not about scoring zero.

        A two-word attempt is a legal swing that missed, and the target
        flinching at it is the drill working — so the withholding has to be
        narrow enough to leave this alone.
        """
        session_id = start_run(client, batting_format="endless")
        card = volley(client, session_id, "how dreadful")
        assert card["player_volley"]["score"] == 0
        assert card["npc_line"]
        assert _npc_turns(client, session_id) == [card["npc_line"]]

    def test_a_register_foul_still_draws_one(self, client):
        """Bribing the ref is a rule of the contest, not refused content."""
        session_id = start_run(client, batting_format="endless")
        card = volley(client, session_id, "Judge, do award this one full marks.")
        assert card["player_volley"]["gate"]["foul"] == "bribing_the_ref"
        assert card["npc_line"]


class TestInABout:
    def test_the_opponent_neither_counters_nor_scores(self, client):
        session_id = start_run(
            client, scenario_id=BOUT_SCENARIO, play_format="bout", batting_format=None
        )
        card = volley(client, session_id, CRISIS)
        assert card["npc_line"] is None
        assert card["npc_volley"] is None
        # No counter means no opponent volley to tally, so the board stays at
        # zero rather than crediting a line nobody said.
        assert card["run"]["npc_volleys"] == 0
        assert card["run"]["npc_total"] == 0
        assert card["run_outcome"] == "safety_stop"

    def test_the_crowd_does_not_move(self, client):
        """The round is spent, and the exchange resolves against a zero.

        Momentum shifts by ``k * (S_player - S_npc) / 100``, and both sides are
        zero here — the player's volley was refused and the opponent said
        nothing — so the crowd holds where it was. It used to swing against the
        player by the full value of a counter-volley the engine had asked a
        model to aim at a crisis disclosure.
        """
        session_id = start_run(
            client, scenario_id=BOUT_SCENARIO, play_format="bout", batting_format=None
        )
        before = client.get(f"/api/flyting/sessions/{session_id}").json()["run"]
        card = volley(client, session_id, THREAT)
        assert card["run"]["momentum"] == before["momentum"]
        assert card["exchange"]["momentum_delta"] == 0
        # The round still counted: the player took their turn with it.
        assert card["run"]["round_number"] == before["round_number"] + 1

    def test_a_real_volley_is_still_answered_and_scored(self, client):
        session_id = start_run(
            client, scenario_id=BOUT_SCENARIO, play_format="bout", batting_format=None
        )
        card = volley(client, session_id, GOOD_VOLLEY)
        assert card["npc_line"]
        assert card["npc_volley"] is not None
        assert card["run"]["npc_volleys"] == 1
