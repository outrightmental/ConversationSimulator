# SPDX-License-Identifier: Apache-2.0
"""A scenario's own state variables and events, wired into play (issue #580).

In the D-05 pre-check the starter model wrote the engine baselines ``trust``
and ``patience`` on almost every turn and a variable only the scenario
defines once in twenty turns, so no meter, event or ending built on the
authored variables ever moved; and no event's ``npc_instruction`` reached a
prompt, because events were evaluated after the reply (P4). These tests pin
the engine half of the fix:

  - which variables a scenario plays (``played_variable_names``): the ones it
    declares, then the baselines its events and endings read; none for a
    scenario that configures no state, which plays every baseline as before;
  - what the prompt is told each means (``prompt_state_variables``);
  - the turn request: the STATE_VARIABLES layer, and a schema whose
    ``state_delta`` requires those variables and takes no other;
  - the state engine rejecting any other variable a runtime still writes;
  - events evaluated on the state the previous turn left, their instructions
    in that turn's prompt, recorded on that turn, once or on every turn their
    condition holds as the event says;
  - the meters: with state of its own a scenario shows only the visible
    variables it plays, because no other can move, on every path that
    reports them (turn, opening, session detail, socket, export, debrief).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

import pytest
import yaml
from fastapi.testclient import TestClient

from convsim_core.app import create_app
from convsim_core.config import ServiceConfig
from convsim_core.edition import DEMO_SCENARIOS
from convsim_core.runtime.fake import FakeChatRuntime
from convsim_core.runtime.types import ChatFinal, ChatRequest, ChatToken
from convsim_core.scenario_state import (
    BASELINE_DESCRIPTIONS,
    BASELINE_VARIABLES,
    ScenarioEvent,
    VariableVisibility,
    apply_state_delta,
    build_variable_defs,
    evaluate_event_triggers,
    hidden_variable_names,
    initialize_state,
    partition_state_by_visibility,
    played_variable_names,
)
from convsim_core.scenarios import (
    SCENARIOS,
    ScenarioInfo,
    load_scenario_info_from_pack,
    prompt_state_variables,
)
from convsim_core.services.turn_pipeline import process_turn
from convsim_core.storage.migrations import run_migrations
from convsim_prompt import NPC_TURN_OUTPUT_SCHEMA, StateVariableCue

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PACKS = _REPO_ROOT / "packs"


def _pack_scenario(pack: str, scenario_id: str) -> ScenarioInfo:
    return load_scenario_info_from_pack(_PACKS / "official" / pack, f"scenarios/{scenario_id}.yaml")


def _scenario_files() -> List[Path]:
    return sorted(_PACKS.glob("*/*/scenarios/*.yaml"))


# ---------------------------------------------------------------------------
# Which variables a scenario plays
# ---------------------------------------------------------------------------


class TestPlayedVariables:
    def test_declared_variables_in_their_order_a_redeclared_baseline_included(self):
        info = _pack_scenario("dating-confidence-boundaries", "the_ask")
        assert played_variable_names(
            info.state_variable_overrides, info.events, info.ending_conditions,
        ) == ["rapport", "confidence", "jordan_interest", "jordan_comfort"]

    def test_baselines_an_event_or_ending_reads_come_after(self):
        """The catalog coworker_feedback declares only rapport, and its event
        and endings read patience and objective_progress."""
        info = SCENARIOS["coworker_feedback"]
        assert played_variable_names(
            info.state_variable_overrides, info.events, info.ending_conditions,
        ) == ["rapport", "patience", "objective_progress"]

    def test_a_baseline_the_scenario_only_hides_is_not_played(self):
        info = SCENARIOS["first_words_tutorial"]
        assert played_variable_names(
            info.state_variable_overrides, info.events, info.ending_conditions,
        ) == ["engagement", "confidence"]
        # Showing a hidden baseline, or the legacy integer form, does declare it.
        assert played_variable_names({"pressure": {"visibility": "visible"}, "trust": 30}) == [
            "pressure", "trust",
        ]

    def test_a_scenario_with_no_state_of_its_own_plays_none(self):
        """Its only variables are the baselines, played free-form as before."""
        for scenario_id in ("behavioral_interview", "hostile_executive_interview",
                            "used_car_negotiation", "spanish_coffee"):
            info = SCENARIOS[scenario_id]
            assert played_variable_names(
                info.state_variable_overrides, info.events, info.ending_conditions,
            ) == [], scenario_id
            assert info.get_scenario_data("standard").state_variables == []

    def test_unknown_and_malformed_conditions_add_nothing(self):
        events = [
            ScenarioEvent(id="a", when={"type": "max_turns", "value": 3}, npc_instruction="x"),
            ScenarioEvent(id="b", when={"type": "variable_above", "variable": "ghost", "threshold": 1}, npc_instruction="x"),
            ScenarioEvent(id="c", when="variable_above", npc_instruction="x"),  # type: ignore[arg-type]
        ]
        assert played_variable_names({"clarity": {"default": 10}}, events, {"success": "x"}) == ["clarity"]

    @pytest.mark.parametrize("scenario_file", _scenario_files(), ids=lambda p: p.stem)
    def test_every_pack_scenario_plays_what_its_events_and_endings_read(self, scenario_file):
        info = load_scenario_info_from_pack(scenario_file.parent.parent, f"scenarios/{scenario_file.name}")
        played = played_variable_names(info.state_variable_overrides, info.events, info.ending_conditions)
        assert played, scenario_file.stem
        read = {e.when.get("variable") for e in info.events or []} | {
            c.get("variable") for c in (info.ending_conditions or {}).values() if isinstance(c, dict)
        }
        assert {r for r in read if r} <= set(played), scenario_file.stem


# ---------------------------------------------------------------------------
# What the prompt says each variable means
# ---------------------------------------------------------------------------


class TestPromptStateVariables:
    def test_an_authored_description_is_carried_and_needs_no_cue(self):
        overrides = {"clarity": {"default": 10, "max_delta_per_turn": 7,
                                 "description": "  How clear the ask is.\n Rises with a number. "}}
        events = [ScenarioEvent(id="e", when={"type": "variable_below", "variable": "clarity", "threshold": 5},
                                npc_instruction="Ask for a number.")]
        assert build_variable_defs(overrides)["clarity"].description == "How clear the ask is. Rises with a number."
        [variable] = prompt_state_variables(overrides, events, None)
        assert (variable.name, variable.min, variable.max, variable.max_delta_per_turn) == ("clarity", 0, 100, 7)
        assert variable.description == "How clear the ask is. Rises with a number."
        assert variable.cues == []

    def test_without_one_the_events_say_what_its_levels_mean(self):
        info = _pack_scenario("everyday-negotiation", "used_car_negotiation")
        overrides = {
            name: {k: v for k, v in spec.items() if k != "description"}
            for name, spec in info.state_variable_overrides.items()
        }
        by_name = {v.name: v for v in prompt_state_variables(overrides, info.events, info.ending_conditions)}
        assert by_name["leverage"].description == ""
        assert by_name["leverage"].cues == [StateVariableCue(
            direction="above", threshold=55,
            text=next(e.npc_instruction for e in info.events if e.id == "research_anchor_reward"),
        )]
        assert [c.direction for c in by_name["perceived_fairness"].cues] == ["below"]
        assert by_name["firmness"].cues == []

    def test_a_baseline_gets_the_engines_own_line_and_its_cues(self):
        info = SCENARIOS["coworker_feedback"]
        by_name = {v.name: v for v in prompt_state_variables(
            info.state_variable_overrides, info.events, info.ending_conditions)}
        assert by_name["patience"].description == BASELINE_DESCRIPTIONS["patience"]
        assert [(c.direction, c.threshold) for c in by_name["patience"].cues] == [("below", 30)]
        assert by_name["rapport"].description == BASELINE_DESCRIPTIONS["rapport"]
        assert set(BASELINE_DESCRIPTIONS) == set(BASELINE_VARIABLES)

    def test_a_threshold_that_is_not_a_number_gives_no_cue(self):
        events = [ScenarioEvent(id="e", when={"type": "variable_above", "variable": "x", "threshold": "high"},
                                npc_instruction="Warm up.")]
        [variable] = prompt_state_variables({"x": {"default": 1}}, events, None)
        assert variable.cues == []

    def test_scenario_data_carries_them_and_a_broken_block_carries_none(self):
        info = _pack_scenario("difficult-conversations", "ask_for_raise")
        data = info.get_scenario_data("hard")
        assert data.state_variable_names == ["impression", "rapport", "evidence_strength", "case_clarity"]
        broken = ScenarioInfo(
            scenario_data=info.scenario_data, max_turns=5, supported_languages=["en"],
            difficulty_options=info.difficulty_options, opening_npc_says="Hi.",
            state_variable_overrides={"x": {"visibility": "sideways"}},
        )
        assert broken.get_scenario_data("standard").state_variables == []


# ---------------------------------------------------------------------------
# The state engine keeps to the session's variables
# ---------------------------------------------------------------------------


class TestApplyStateDelta:
    def test_a_known_variable_outside_the_allowed_ones_is_rejected(self):
        defs = build_variable_defs({"impression": {"default": 50, "max_delta_per_turn": 6}})
        state = initialize_state(defs)
        result = apply_state_delta(state, {"impression": 9, "trust": 10, "ghost": 3}, defs,
                                   allowed=["impression"])
        assert result.actual_changes == {"impression": 6}
        assert result.rejected_keys == ["trust", "ghost"]
        assert result.new_state["trust"] == 50

    def test_without_allowed_every_known_variable_moves_as_before(self):
        defs = build_variable_defs()
        result = apply_state_delta(initialize_state(defs), {"trust": 10, "ghost": 3}, defs)
        assert result.actual_changes == {"trust": 10}
        assert result.rejected_keys == ["ghost"]


# ---------------------------------------------------------------------------
# The meters show what the scenario plays
# ---------------------------------------------------------------------------


def _visible_played(info: ScenarioInfo) -> List[str]:
    defs = build_variable_defs(info.state_variable_overrides)
    return [n for n in info.played_variables() if defs[n].visibility == VariableVisibility.VISIBLE]


class TestMeters:
    def test_a_variable_outside_the_played_ones_is_hidden(self):
        defs = build_variable_defs({"mood": {"default": 40}, "secret": {"default": 5, "visibility": "hidden"}})
        visible, hidden = partition_state_by_visibility(
            initialize_state(defs), defs, ["mood", "secret", "rapport"],
        )
        assert visible == {"rapport": 50, "mood": 40}
        assert set(hidden) == {"secret", "trust", "patience", "pressure", "openness", "objective_progress"}
        assert hidden_variable_names(defs, ["mood", "secret", "rapport"]) == set(hidden)

    @pytest.mark.parametrize("played", [None, []])
    def test_without_played_ones_each_keeps_its_own_visibility(self, played):
        defs = build_variable_defs({"trust": {"visibility": "hidden"}})
        visible, hidden = partition_state_by_visibility(initialize_state(defs), defs, played)
        assert set(hidden) == {"trust", "pressure"}
        assert set(visible) == {"patience", "rapport", "openness", "objective_progress"}
        assert hidden_variable_names(defs, played) == {"trust", "pressure"}

    @pytest.mark.parametrize("scenario_file", _scenario_files(), ids=lambda p: p.stem)
    def test_every_pack_scenario_shows_only_its_visible_played_variables(self, scenario_file):
        info = load_scenario_info_from_pack(scenario_file.parent.parent, f"scenarios/{scenario_file.name}")
        assert info.played_variables() == [v.name for v in info.get_scenario_data("standard").state_variables]
        defs = build_variable_defs(info.state_variable_overrides)
        visible, _ = partition_state_by_visibility(initialize_state(defs), defs, info.played_variables())
        assert sorted(visible) == sorted(_visible_played(info)), scenario_file.stem
        assert visible, f"{scenario_file.stem} shows no meter at all"

    def test_the_catalog_keeps_its_baselines_unless_it_plays_its_own(self):
        defs = build_variable_defs()
        for scenario_id in ("behavioral_interview", "hostile_executive_interview",
                            "used_car_negotiation", "spanish_coffee"):
            info = SCENARIOS[scenario_id]
            visible, _ = partition_state_by_visibility(initialize_state(defs), defs, info.played_variables())
            assert set(visible) == {"trust", "patience", "rapport", "openness", "objective_progress"}
        # coworker_feedback plays three baselines: trust and openness never move.
        info = SCENARIOS["coworker_feedback"]
        defs = build_variable_defs(info.state_variable_overrides)
        visible, _ = partition_state_by_visibility(initialize_state(defs), defs, info.played_variables())
        assert set(visible) == {"rapport", "patience", "objective_progress"}

    def test_a_broken_state_block_hides_nothing_more(self):
        info = _pack_scenario("difficult-conversations", "ask_for_raise")
        broken = ScenarioInfo(
            scenario_data=info.scenario_data, max_turns=5, supported_languages=["en"],
            difficulty_options=info.difficulty_options, opening_npc_says="Hi.",
            state_variable_overrides={"x": {"visibility": "sideways"}},
        )
        assert broken.played_variables() == []


# ---------------------------------------------------------------------------
# process_turn: the request, the delta, and the events
# ---------------------------------------------------------------------------


class _ScriptedRuntime(FakeChatRuntime):
    """Answers each turn with the next of ``replies`` and records every request."""

    def __init__(self, *replies: Dict[str, Any]) -> None:
        super().__init__()
        self.replies = list(replies)
        self.requests: List[ChatRequest] = []

    def chat_stream(self, request: ChatRequest):
        self.requests.append(request)
        return self._respond()

    async def _respond(self) -> AsyncGenerator:
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        response = {
            "npc_utterance": "Go on.",
            "npc_emotion": "neutral",
            "state_delta": reply.get("state_delta", {}),
            "event_flags": reply.get("event_flags", []),
            "rubric_observations": [],
            "safety": {"status": "ok"},
            "session_control": {"continue_session": True},
        }
        text = json.dumps(response)
        yield ChatFinal(text=text, model_id="fake-small", input_tokens=10,
                        output_tokens=len(text.split()), structured=response)

    def system_prompts(self) -> List[str]:
        return [r.messages[0].content for r in self.requests]


def _unit_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    run_migrations(conn)
    conn.execute(
        "INSERT INTO turn_sessions (session_id, scenario_id, flow_state, state_vars_json, "
        "fired_events_json, turn_count, setup_json) "
        "VALUES ('s', 'x', 'PlayerTurnListening', '{}', '[]', 0, '{}')"
    )
    conn.commit()
    return conn


async def _play(info: ScenarioInfo, runtime: _ScriptedRuntime, turns: int, conn=None):
    conn = conn or _unit_db()
    results = []
    for n in range(turns):
        row = conn.execute("SELECT * FROM turn_sessions WHERE session_id = 's'").fetchone()
        results.append(await process_turn(
            session_row=row,
            player_text=f"Line {n + 1}.",
            scenario_data=info.get_scenario_data("standard"),
            max_turns=info.max_turns,
            runtime=runtime,
            conn=conn,
            state_variable_overrides=info.state_variable_overrides,
            scenario_events=info.events,
            ending_conditions=info.ending_conditions,
        ))
    return results, conn


def _scenario(variables: Dict[str, Any], events: List[ScenarioEvent], max_turns: int = 10) -> ScenarioInfo:
    base = SCENARIOS["behavioral_interview"]
    return ScenarioInfo(
        scenario_data=base.scenario_data, max_turns=max_turns, supported_languages=["en"],
        difficulty_options=base.difficulty_options, opening_npc_says="Hello.",
        state_variable_overrides=variables, events=events,
    )


class TestTheTurnRequest:
    @pytest.mark.asyncio
    async def test_a_pack_scenario_is_sent_its_variables_required_and_closed(self):
        info = _pack_scenario("everyday-negotiation", "used_car_negotiation")
        runtime = _ScriptedRuntime({"state_delta": {"leverage": 10, "trust": 10}})
        [result], conn = await _play(info, runtime, 1)
        [request] = runtime.requests
        delta = request.json_schema["properties"]["state_delta"]
        names = ["deal_progress", "perceived_fairness", "firmness", "concession_level", "leverage"]
        assert delta["required"] == names and list(delta["properties"]) == names
        assert delta["additionalProperties"] is False
        assert delta["properties"]["firmness"] == {"type": "integer"}
        system = request.messages[0].content
        assert system.index("--- LAYER:STATE_VARIABLES ---") < system.index("--- LAYER:CURRENT_STATE ---")
        assert "  - leverage (0-100, ±20 a turn): " in system
        assert "  - firmness (0-100, ±12 a turn)" in system
        # CURRENT_STATE leaves out the baselines the scenario never reads.
        current = system.split("--- LAYER:CURRENT_STATE ---")[1].split("--- LAYER:")[0]
        assert "trust" not in current and "  leverage: 30" in current
        # The schema the prompt quotes is the one sent.
        assert json.dumps(request.json_schema, indent=2) in system
        # A baseline the schema does not take is rejected, not applied.
        assert result.state_delta == {"leverage": 10}
        assert result.new_state_vars["trust"] == 50
        # The meters are the visible variables it plays: no frozen baseline.
        assert result.visible_state == {"deal_progress": 0, "concession_level": 0}
        [payload] = [json.loads(r["payload_json"]) for r in conn.execute(
            "SELECT payload_json FROM turn_session_events WHERE event_type = 'state_delta'")]
        assert payload["rejected_keys"] == ["trust"]

    @pytest.mark.asyncio
    async def test_a_scenario_with_no_state_of_its_own_is_sent_the_canonical_schema(self):
        info = SCENARIOS["behavioral_interview"]
        runtime = _ScriptedRuntime({"state_delta": {"trust": 5}})
        [result], _ = await _play(info, runtime, 1)
        assert runtime.requests[0].json_schema == NPC_TURN_OUTPUT_SCHEMA
        assert "LAYER:STATE_VARIABLES" not in runtime.system_prompts()[0]
        assert result.state_delta == {"trust": 5}


class TestEventsBeforeTheTurn:
    @pytest.mark.asyncio
    async def test_an_event_fires_on_the_turn_after_the_state_crosses(self):
        event = ScenarioEvent(id="warm", npc_instruction="Warm up noticeably.",
                              when={"type": "variable_above", "variable": "mood", "threshold": 60})
        info = _scenario({"mood": {"default": 50, "max_delta_per_turn": 20}}, [event])
        runtime = _ScriptedRuntime({"state_delta": {"mood": 15}})
        results, conn = await _play(info, runtime, 3)
        assert [r.triggered_scenario_events for r in results] == [[], ["warm"], []]
        prompts = runtime.system_prompts()
        assert "LAYER:SCENARIO_EVENTS" not in prompts[0]
        assert "--- LAYER:SCENARIO_EVENTS ---\n" in prompts[1]
        assert "  - Warm up noticeably." in prompts[1]
        # Once: it does not come back on the next turn.
        assert "LAYER:SCENARIO_EVENTS" not in prompts[2]
        # The variable's line says what the event means throughout.
        assert all("  - mood (0-100, ±20 a turn): above 60: Warm up noticeably." in p for p in prompts)
        rows = conn.execute(
            "SELECT turn_number, payload_json FROM turn_session_events WHERE event_type = 'scenario_event'"
        ).fetchall()
        assert [(r["turn_number"], json.loads(r["payload_json"])) for r in rows] == [(2, {"event_id": "warm"})]
        fired = conn.execute("SELECT fired_events_json FROM turn_sessions WHERE session_id = 's'").fetchone()
        assert json.loads(fired[0]) == ["warm"]

    @pytest.mark.asyncio
    async def test_an_event_true_at_the_start_fires_on_turn_one(self):
        event = ScenarioEvent(id="probe", npc_instruction="Probe the gap.",
                              when={"type": "variable_below", "variable": "gap", "threshold": 1})
        info = _scenario({"gap": {"default": 0, "max": 5}}, [event])
        results, _ = await _play(info, _ScriptedRuntime({"state_delta": {"gap": 1}}), 2)
        assert [r.triggered_scenario_events for r in results] == [["probe"], []]

    @pytest.mark.asyncio
    async def test_a_repeating_event_speaks_on_every_turn_its_condition_holds(self):
        event = ScenarioEvent(id="push", npc_instruction="Hold your ground.", repeat=True,
                              when={"type": "variable_below", "variable": "fairness", "threshold": 40})
        info = _scenario({"fairness": {"default": 50, "max_delta_per_turn": 15}}, [event])
        runtime = _ScriptedRuntime(
            {"state_delta": {"fairness": -15}},  # 35 after turn 1
            {"state_delta": {"fairness": 0}},    # still 35
            {"state_delta": {"fairness": 15}},   # 50 after turn 3
            {"state_delta": {"fairness": 0}},
        )
        results, _ = await _play(info, runtime, 4)
        assert [r.triggered_scenario_events for r in results] == [[], ["push"], ["push"], []]
        assert ["  - Hold your ground." in p for p in runtime.system_prompts()] == [False, True, True, False]

    @pytest.mark.asyncio
    async def test_a_flag_event_reads_the_flags_of_the_reply_before(self):
        event = ScenarioEvent(id="noticed", npc_instruction="Mention the window seat.",
                              when={"type": "flag", "flag_id": "window_seat"})
        info = _scenario({"mood": {"default": 50}}, [event])
        runtime = _ScriptedRuntime({"event_flags": ["window_seat"]}, {"event_flags": []})
        results, _ = await _play(info, runtime, 3)
        assert [r.triggered_scenario_events for r in results] == [[], ["noticed"], []]

    @pytest.mark.asyncio
    async def test_a_turn_count_event_fires_on_that_turn(self):
        event = ScenarioEvent(id="late", npc_instruction="Start wrapping up.",
                              when={"type": "max_turns", "value": 2})
        info = _scenario({"mood": {"default": 50}}, [event])
        results, _ = await _play(info, _ScriptedRuntime({}), 3)
        assert [r.triggered_scenario_events for r in results] == [[], ["late"], []]

    @pytest.mark.asyncio
    async def test_instructions_follow_the_scenarios_event_order(self):
        events = [
            ScenarioEvent(id="b", npc_instruction="Second.", when={"type": "max_turns", "value": 1}),
            ScenarioEvent(id="a", npc_instruction="First?", when={"type": "max_turns", "value": 1}),
        ]
        info = _scenario({"mood": {"default": 50}}, events)
        runtime = _ScriptedRuntime({})
        [result], _ = await _play(info, runtime, 1)
        assert result.triggered_scenario_events == ["b", "a"]
        prompt = runtime.system_prompts()[0]
        assert prompt.index("  - Second.") < prompt.index("  - First?")


# ---------------------------------------------------------------------------
# End to end through the API
# ---------------------------------------------------------------------------


# Events that are meant to speak in the first reply. Every other event a pack
# or the catalog authors waits for a turn that earns it: since events reach the
# prompt (issue #580), one true at the defaults directs the NPC's first reply
# whatever the player said.
_FIRST_REPLY_EVENTS = {
    # The opening asks "What did you want to say?"; the player's first line is
    # the no, and Ryan's lighter reframe is the first test of it.
    ("holding_your_ground", "first_test"),
    # Victor challenges every claim until credibility (35) reaches 50; his
    # opening already demands what the candidate decided, and why.
    ("hostile_executive_interview", "credibility_challenge"),
}


def _every_scenario() -> List[Any]:
    packs = [pytest.param(f, id=f.stem) for f in _scenario_files()]
    catalog = [pytest.param(sid, id=f"catalog-{sid}") for sid in SCENARIOS]
    return packs + catalog


@pytest.mark.parametrize("source", _every_scenario())
def test_no_event_is_true_at_the_defaults_unless_meant_for_the_first_reply(source) -> None:
    if isinstance(source, Path):
        info = load_scenario_info_from_pack(source.parent.parent, f"scenarios/{source.name}")
        scenario_id = source.stem
    else:
        info, scenario_id = SCENARIOS[source], source
    state = initialize_state(build_variable_defs(info.state_variable_overrides))
    fired = evaluate_event_triggers(state, 1, info.events or [], set())
    unexpected = [e for e in fired if (scenario_id, e) not in _FIRST_REPLY_EVENTS]
    assert unexpected == [], f"{scenario_id}: true at the defaults: {unexpected}"


def test_the_first_reply_events_still_are():
    """The exceptions are pinned: each is in its pack and true at the defaults."""
    found = set()
    for path in _scenario_files():
        info = load_scenario_info_from_pack(path.parent.parent, f"scenarios/{path.name}")
        state = initialize_state(build_variable_defs(info.state_variable_overrides))
        found |= {(path.stem, e) for e in evaluate_event_triggers(state, 1, info.events or [], set())}
    assert found == _FIRST_REPLY_EVENTS


def test_elena_comes_back_to_the_gap_on_turn_three():
    """stretch_role_interview's gap_probing was true at gap_acknowledged's
    default (0 < 1), so Elena's first reply raised the gap, even after a
    candidate who had just addressed it."""
    info = _pack_scenario("job-interview-basic", "stretch_role_interview")
    event = next(e for e in info.events if e.id == "gap_probing")
    state = initialize_state(build_variable_defs(info.state_variable_overrides))
    fired: set = set()
    assert [evaluate_event_triggers(state, turn, [event], fired) for turn in range(1, 6)] == [
        [], [], ["gap_probing"], [], [],
    ]
    text = " ".join(event.npc_instruction.split())
    assert "If the candidate has not yet addressed it directly" in text
    assert "If they already have" in text
    variable = next(v for v in prompt_state_variables(
        info.state_variable_overrides, info.events, info.ending_conditions) if v.name == "gap_acknowledged")
    assert variable.description.startswith("Whether the candidate has addressed the experience gap")


class _RecordingRuntime(FakeChatRuntime):
    """Writes ask_for_raise's variables and a baseline, and records every request."""

    def __init__(self) -> None:
        self.requests: List[ChatRequest] = []

    def chat_stream(self, request: ChatRequest) -> Any:
        self.requests.append(request)
        return self._respond(request)

    async def _respond(self, request: ChatRequest) -> AsyncGenerator:
        schema = request.json_schema or {}
        if "replay_suggestions" in (schema.get("properties") or {}):
            response: Optional[Dict[str, Any]] = {
                "summary": "You named a figure.", "dimension_bands": {},
                "strengths": ["s"], "improvements": ["i"], "turning_points": [],
                "replay_suggestions": ["r"],
            }
        else:
            # A different line each turn: the repetition guard (issue #580)
            # retries a reply that repeats the NPC's last line, which would
            # add a request this test does not count.
            turn = sum(
                1 for r in self.requests
                if "replay_suggestions" not in ((r.json_schema or {}).get("properties") or {})
            )
            response = {
                "npc_utterance": (
                    "Where does that number come from?",
                    "And who else has seen those figures?",
                    "Walk me through how you would measure that next quarter.",
                )[(turn - 1) % 3],
                "npc_emotion": "skeptical",
                "state_delta": {"evidence_strength": -12, "case_clarity": 8, "impression": 2,
                                "rapport": 0, "trust": 9},
                "event_flags": [],
                "rubric_observations": [],
                "safety": {"status": "ok"},
                "session_control": {"continue_session": True},
            }
        text = json.dumps(response)
        for word in text.split():
            yield ChatToken(text=word + " ")
        yield ChatFinal(text=text, model_id="fake-small", input_tokens=10,
                        output_tokens=len(text.split()), structured=response)


@pytest.fixture()
def app(tmp_path):
    config = ServiceConfig(
        host="127.0.0.1",
        port=7355,
        data_dir=str(tmp_path / "data"),
        log_dir=str(tmp_path / "logs"),
        db_dir=str(tmp_path / "db"),
        packs_dir=str(tmp_path / "packs"),
        official_packs_dir=str(_PACKS / "official"),
    )
    return create_app(config)


def test_ask_for_raise_plays_its_own_state_and_events(app) -> None:
    """ask_for_raise is not in the hardcoded catalog, so even the full app plays
    it from its pack. evidence_strength falls below 10 on turn 1, so its
    repeating probe speaks on turns 2 and 3."""
    from convsim_core.services.model_manager_service import set_active_config

    runtime = _RecordingRuntime()
    with TestClient(app) as client:
        set_active_config(app.state.db.connection(), runtime_id="llama_cpp", model_id="/tmp/model.gguf")
        res = client.post("/api/sessions", json={
            "scenario_id": "ask_for_raise", "difficulty": "standard", "player_role_name": "Alex",
            "language": "en", "input_mode": "text-only", "tts_enabled": False,
            "show_state_meters": True, "save_transcript": True, "seed": None,
        })
        assert res.status_code == 201, res.text
        session_id = res.json()["session_id"]
        assert client.post(f"/api/sessions/{session_id}/start").status_code == 200
        app.state.runtime = runtime
        payloads = []
        for n in range(3):
            res = client.post(f"/api/sessions/{session_id}/turn", json={"content": f"I deserve more ({n})."})
            assert res.status_code == 200, res.text
            payloads.append(next(e for e in res.json()["events"] if e["event_type"] == "npc_turn")["payload"])
        client.post(f"/api/sessions/{session_id}/end")
        debrief = client.post(f"/api/sessions/{session_id}/debrief")
    assert debrief.status_code == 200, debrief.text

    turns = [r for r in runtime.requests if "replay_suggestions" not in (r.json_schema or {}).get("properties", {})]
    assert len(turns) == 3
    for request in turns:
        assert request.json_schema["properties"]["state_delta"]["required"] == [
            "impression", "rapport", "evidence_strength", "case_clarity",
        ]
        assert "--- LAYER:STATE_VARIABLES ---" in request.messages[0].content
    probe = next(e for e in yaml.safe_load(
        (_PACKS / "official/difficult-conversations/scenarios/ask_for_raise.yaml").read_text()
    )["events"] if e["id"] == "vague_claim_probe")
    probe_line = "  - " + " ".join(probe["npc_instruction"].split())
    assert [probe_line in r.messages[0].content for r in turns] == [False, True, True]
    assert [p["triggered_scenario_events"] for p in payloads] == [[], ["vague_claim_probe"], ["vague_claim_probe"]]
    # The baseline the scenario never reads stays where it started, and
    # has no meter.
    assert payloads[-1]["state_delta"].get("trust") is None
    assert [sorted(p["visible_state"]) for p in payloads] == [["impression", "rapport"]] * 3


class _EveryVariableRuntime(FakeChatRuntime):
    """Moves every variable the turn schema names by +4, and writes a baseline.

    It answers under the llama.cpp id: the demo plays only on its managed
    engine and refuses a session on any other live runtime.
    """

    @property
    def id(self) -> str:
        return "llama_cpp"

    async def _respond(self, request: ChatRequest) -> AsyncGenerator:
        schema = request.json_schema or {}
        if "replay_suggestions" in (schema.get("properties") or {}):
            response: Dict[str, Any] = {
                "summary": "You kept going.", "dimension_bands": {},
                "strengths": ["s"], "improvements": ["i"], "turning_points": [],
                "replay_suggestions": ["r"],
            }
        else:
            names = schema["properties"]["state_delta"].get("properties") or {}
            response = {
                "npc_utterance": "Go on.",
                "npc_emotion": "neutral",
                "state_delta": {**{n: 4 for n in names}, "trust": 9},
                "event_flags": [],
                "rubric_observations": [],
                "safety": {"status": "ok"},
                "session_control": {"continue_session": True},
            }
        text = json.dumps(response)
        yield ChatFinal(text=text, model_id="fake-small", input_tokens=10,
                        output_tokens=len(text.split()), structured=response)

    def chat_stream(self, request: ChatRequest) -> Any:
        return self._respond(request)


@pytest.fixture()
def demo_app(tmp_path):
    config = ServiceConfig(
        host="127.0.0.1",
        port=7355,
        data_dir=str(tmp_path / "data"),
        log_dir=str(tmp_path / "logs"),
        db_dir=str(tmp_path / "db"),
        packs_dir=str(tmp_path / "packs"),
        official_packs_dir=str(_PACKS / "official"),
        edition="demo",
    )
    return create_app(config)


# The two meters each demo card shows: its visible played variables.
_DEMO_METERS = {
    "behavioral_interview": {"impression", "rapport"},
    "used_car_negotiation": {"deal_progress", "concession_level"},
    "ask_for_raise": {"impression", "rapport"},
    "the_ask": {"rapport", "confidence"},
    "spanish_coffee": {"comprehension", "confidence"},
}


@pytest.mark.parametrize("demo", DEMO_SCENARIOS, ids=lambda d: d.scenario_id)
def test_a_demo_scenario_reports_only_the_meters_it_plays(demo_app, demo) -> None:
    """Every path that reports meters reports the same visible played variables.

    The opening event, the session detail before and after a turn, the turn
    result, the socket's resync, the export and the debrief's state arc.
    Before, the baselines the scenario never reads were reported beside its
    own two, where no delta could ever move them (issue #580).
    """
    from convsim_core.services.model_manager_service import set_active_config

    info = load_scenario_info_from_pack(
        _PACKS / "official" / next(p.parent.parent.name for p in _scenario_files()
                                   if p.stem == demo.scenario_id),
        f"scenarios/{demo.scenario_id}.yaml",
    )
    expected = set(_visible_played(info))
    assert expected == _DEMO_METERS[demo.scenario_id]

    with TestClient(demo_app) as client:
        set_active_config(demo_app.state.db.connection(), runtime_id="llama_cpp", model_id="/tmp/model.gguf")
        demo_app.state.runtime = _EveryVariableRuntime()
        res = client.post("/api/sessions", json={
            "scenario_id": demo.scenario_id, "difficulty": "standard", "player_role_name": "Alex",
            "language": info.supported_languages[0], "input_mode": "text-only", "tts_enabled": False,
            "show_state_meters": True, "save_transcript": True, "seed": None,
        })
        assert res.status_code == 201, res.text
        session_id = res.json()["session_id"]
        start = client.post(f"/api/sessions/{session_id}/start")
        assert start.status_code == 200, start.text
        opening = next(e for e in start.json()["events"] if e["event_type"] == "npc_opening")
        assert set(opening["payload"]["visible_state"]) == expected
        assert set(client.get(f"/api/sessions/{session_id}").json()["visible_state"]) == expected

        res = client.post(f"/api/sessions/{session_id}/turn", json={"content": "Hello, thanks for meeting me."})
        assert res.status_code == 200, res.text
        turn = next(e for e in res.json()["events"] if e["event_type"] == "npc_turn")["payload"]
        assert set(turn["visible_state"]) == expected
        assert set(turn["state_delta"]) == set(info.played_variables())
        assert set(client.get(f"/api/sessions/{session_id}").json()["visible_state"]) == expected
        with client.websocket_connect(f"/ws/session/{session_id}") as ws:
            resync = ws.receive_json()
        assert resync["type"] == "session.state"
        assert set(resync["payload"]["state_vars"]) == expected

        client.post(f"/api/sessions/{session_id}/end")
        assert set(client.get(f"/api/sessions/{session_id}/export").json()["visible_state"]) == expected
        debrief = client.post(f"/api/sessions/{session_id}/debrief")
    assert debrief.status_code == 200, debrief.text
    arc = debrief.json()["metrics"]["state_arc"]
    assert arc and all(set(point["state"]) == expected for point in arc)
