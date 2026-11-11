# SPDX-License-Identifier: Apache-2.0
"""The scenario rubric, from the pack file to the debrief scorecard (issue #578).

On the starter model every debrief scored dimensions the model had made up
turn by turn (one session: "Experience Gap, Learning Velocity, Self-Awareness,
Transferable Skills, Self Awareness"), at 50 give or take a few points, and the
telemetry showed hidden state next to the scores (issue #580, P6). These tests
pin the engine half of the fix:

  - every pack scenario's rubric loads with the scenario, and a missing or
    broken one leaves it without a rubric rather than unplayable;
  - a scenario with a rubric is scored on its dimensions only, from the
    debrief's bands plus the turns' notes, and weighted by the rubric;
  - the turn and debrief requests carry the session's schemas, with the
    rubric ids as enums;
  - hidden state variables stay out of the debrief telemetry;
  - a scenario with no rubric (the hardcoded catalog) plays and debriefs as
    it always has.
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
from convsim_core.runtime.fake import FakeChatRuntime
from convsim_core.runtime.types import ChatFinal, ChatRequest, ChatToken
from convsim_core.scenarios import SCENARIOS, load_scenario_info_from_pack, rubric_from_yaml
from convsim_core.services.debrief_engine import (
    BAND_ADJUST_MAX,
    BAND_SCORES,
    _compute_overall_score,
    _compute_scores,
    _hidden_variables,
    _rubric_bands,
    compute_metrics,
)
from convsim_prompt import (
    DEBRIEF_NARRATIVE_SCHEMA,
    NPC_TURN_OUTPUT_SCHEMA,
    DebriefNarrative,
    RubricDimension,
    ScenarioRubric,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PACKS = _REPO_ROOT / "packs"


def _scenario_files() -> List[Path]:
    return sorted(_PACKS.glob("*/*/scenarios/*.yaml"))


def _rubric_doc(scenario_file: Path) -> Optional[Dict[str, Any]]:
    raw = yaml.safe_load(scenario_file.read_text(encoding="utf-8")) or {}
    ref = (raw.get("rubric") or {}).get("ref")
    if not ref:
        return None
    return yaml.safe_load((scenario_file.parent / ref).read_text(encoding="utf-8"))


def _rubric(*dims: tuple) -> ScenarioRubric:
    """A rubric of (id, name, weight) dimensions."""
    return ScenarioRubric(rubric_id="r", title="R", dimensions=[
        RubricDimension(id=i, name=n, weight=w) for i, n, w in dims
    ])


_RAISE = _rubric(
    ("business_case", "Business Case", 0.35),
    ("specificity", "Specificity", 0.30),
    ("composure", "Composure", 0.20),
    ("listening", "Listening", 0.15),
)


class _Row(dict):
    def __getitem__(self, key):
        return dict.__getitem__(self, key)


def _npc_row(*observations: Dict[str, Any], turn_number: int = 2) -> _Row:
    return _Row(
        role="npc",
        raw_output_json=json.dumps({"rubric_observations": list(observations)}),
        state_delta_json="{}",
        event_flags_json="[]",
        safety_json='{"status": "ok"}',
        turn_number=turn_number,
    )


def _obs(rubric_id: str, delta: Optional[int] = None) -> Dict[str, Any]:
    obs: Dict[str, Any] = {"rubric_id": rubric_id, "observation": "x"}
    if delta is not None:
        obs["score_delta"] = delta
    return obs


# ---------------------------------------------------------------------------
# Loading the rubric with the scenario
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "scenario_file", _scenario_files(), ids=lambda p: f"{p.parents[1].name}/{p.stem}"
)
def test_every_pack_scenario_loads_its_rubric(scenario_file: Path) -> None:
    doc = _rubric_doc(scenario_file)
    info = load_scenario_info_from_pack(scenario_file.parents[1], f"scenarios/{scenario_file.name}")
    rubric = info.get_scenario_data("standard").rubric
    if doc is None:
        assert rubric is None
        return
    assert rubric is not None, scenario_file
    assert rubric.rubric_id == doc["rubric_id"]
    assert [(d.id, d.name, d.weight) for d in rubric.dimensions] == [
        (d["id"], d["name"], d.get("weight")) for d in doc["dimensions"]
    ]
    for loaded, authored in zip(rubric.dimensions, doc["dimensions"]):
        assert (loaded.low, loaded.medium, loaded.high) == (
            authored["scoring"]["low"].strip(),
            authored["scoring"]["medium"].strip(),
            authored["scoring"]["high"].strip(),
        )
    # Every difficulty preset carries it.
    for preset in info.difficulty_options:
        assert info.get_scenario_data(preset).rubric is rubric


def test_the_five_demo_scenarios_all_have_a_rubric() -> None:
    """So the D-05 replay's rubric check (d) can be a hard failure."""
    from convsim_core.edition import DEMO_SCENARIOS

    packs = {
        yaml.safe_load((m.parent / "manifest.yaml").read_text(encoding="utf-8"))["pack_id"]: m.parent
        for m in (_PACKS / "official").glob("*/manifest.yaml")
    }
    assert len(DEMO_SCENARIOS) == 5
    for entry in DEMO_SCENARIOS:
        info = load_scenario_info_from_pack(packs[entry.pack_id], f"scenarios/{entry.scenario_id}.yaml")
        assert info.scenario_data.rubric is not None, entry
        assert len(info.scenario_data.rubric.dimensions) >= 4, entry


@pytest.mark.parametrize(
    "scenario_file",
    [f for f in _scenario_files() if _rubric_doc(f) is not None],
    ids=lambda p: f"{p.parents[1].name}/{p.stem}",
)
def test_the_rubric_layer_stays_short(scenario_file: Path) -> None:
    """The layer is read on the first turn of every session (and again on any
    turn the prompt cache misses): one line of at most 24 words per dimension,
    at most about 260 tokens at the composer's four-characters-per-token estimate."""
    from convsim_prompt.layers import build_rubric_layer

    info = load_scenario_info_from_pack(scenario_file.parents[1], f"scenarios/{scenario_file.name}")
    layer = build_rubric_layer(info.get_scenario_data("standard"))
    lines = layer.splitlines()
    dims = [line for line in lines if line.startswith("  - ")]
    assert len(dims) == len(info.scenario_data.rubric.dimensions)
    for line in dims:
        _, brief = line.split(": ", 1)
        assert len(brief.removesuffix(" …").split()) <= 24, line
        assert brief.count("(") == brief.count(")"), line
        assert brief.count('"') % 2 == 0, line
    assert len(layer) // 4 <= 260


def test_the_hardcoded_catalog_has_no_rubric() -> None:
    """Catalog entries keep the old, rubric-less scoring (and the full app
    plays them catalog-first)."""
    for scenario_id, info in SCENARIOS.items():
        assert info.get_scenario_data("standard").rubric is None, scenario_id


def _write_pack(tmp_path: Path, rubric_ref: Optional[str], rubric_text: Optional[str] = None) -> Path:
    pack = tmp_path / "pack"
    (pack / "scenarios").mkdir(parents=True)
    (pack / "rubrics").mkdir()
    scenario = {
        "scenario_id": "s", "title": "S",
        "player_role": {"label": "Player", "brief": "b"},
        "npc": {"display_name": "N", "public_persona": {"occupation": "o"}},
    }
    if rubric_ref is not None:
        scenario["rubric"] = {"ref": rubric_ref}
    (pack / "scenarios" / "s.yaml").write_text(yaml.safe_dump(scenario), encoding="utf-8")
    if rubric_text is not None:
        (pack / "rubrics" / "r.yaml").write_text(rubric_text, encoding="utf-8")
    return pack


@pytest.mark.parametrize("ref, text", [
    ("../rubrics/missing.yaml", None),
    ("../rubrics/r.yaml", "dimensions: [unclosed"),
    ("../rubrics/r.yaml", "dimensions: []"),
    ("../rubrics/r.yaml", "- just a list"),
    ("../../outside.yaml", None),
    ("", None),
])
def test_a_rubric_that_cannot_be_used_leaves_the_scenario_playable(tmp_path, ref, text) -> None:
    (tmp_path / "outside.yaml").write_text(
        "rubric_id: x\ntitle: X\ndimensions:\n  - {id: a, name: A, scoring: {low: l, medium: m, high: h}}\n",
        encoding="utf-8",
    )
    info = load_scenario_info_from_pack(_write_pack(tmp_path, ref, text), "scenarios/s.yaml")
    assert info.scenario_data.rubric is None
    assert info.scenario_data.title == "S"


def test_rubric_parsing_is_lenient_per_dimension() -> None:
    rubric = rubric_from_yaml({
        "rubric_id": "r", "title": "R",
        "dimensions": [
            {"id": "clarity", "name": " Clarity ", "description": "d",
             "scoring": {"low": "l", "medium": "m", "high": "h"}, "weight": 0.4},
            {"id": "Bad Id", "name": "Bad"},
            {"id": "clarity", "name": "Duplicate"},
            "not a dict",
            {"id": "pace", "weight": True},
            {"id": "tone", "weight": 1.5, "scoring": "not a dict"},
            {"id": "depth", "weight": 0},
        ],
    })
    assert rubric is not None
    assert [(d.id, d.name, d.weight) for d in rubric.dimensions] == [
        ("clarity", "Clarity", 0.4), ("pace", "pace", None), ("tone", "tone", None), ("depth", "depth", 0.0),
    ]
    assert (rubric.dimensions[0].low, rubric.dimensions[0].high) == ("l", "h")
    assert rubric.dimensions[2].high == ""
    assert rubric_from_yaml({"dimensions": [{"id": "Nope"}]}) is None
    assert rubric_from_yaml(None) is None


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


class TestScoresWithARubric:
    def test_only_rubric_dimensions_are_scored_in_rubric_order(self) -> None:
        rows = [
            _npc_row(_obs("listening", 1), _obs("experience_gap", 3), _obs("business_case", 2)),
            _npc_row(_obs("Business Case", 1), _obs("transferable_skills", -2)),
        ]
        scores = _compute_scores(rows, _RAISE)
        assert list(scores) == ["business_case", "listening"]
        assert scores == {"business_case": 53.0, "listening": 51.0}

    def test_a_band_sets_the_score_and_the_notes_move_it(self) -> None:
        rows = [_npc_row(_obs("business_case", 3), _obs("specificity", -2))] * 2
        bands = {"business_case": "high", "specificity": "medium", "composure": "low"}
        scores = _compute_scores(rows, _RAISE, bands)
        assert scores == {
            "business_case": BAND_SCORES["high"] + 6,
            "specificity": BAND_SCORES["medium"] - 4,
            "composure": BAND_SCORES["low"],
        }

    def test_the_notes_never_move_a_band_out_of_its_colour_zone(self) -> None:
        many_up = [_npc_row(_obs("composure", 3))] * 10
        many_down = [_npc_row(_obs("business_case", -3))] * 10
        scores = _compute_scores(many_up + many_down, _RAISE, {"composure": "low", "business_case": "high"})
        assert scores["composure"] == BAND_SCORES["low"] + BAND_ADJUST_MAX
        assert scores["business_case"] == BAND_SCORES["high"] - BAND_ADJUST_MAX
        # Red below 40, orange to 69, green from 70 (Debrief.tsx DimensionRow).
        assert BAND_SCORES["low"] + BAND_ADJUST_MAX < 40
        assert 40 <= BAND_SCORES["medium"] - BAND_ADJUST_MAX and BAND_SCORES["medium"] + BAND_ADJUST_MAX < 70
        assert BAND_SCORES["high"] - BAND_ADJUST_MAX >= 70

    def test_a_dimension_with_no_band_is_scored_from_its_notes_or_left_off(self) -> None:
        rows = [_npc_row(_obs("specificity", 2))]
        bands = {"specificity": "not_observed", "listening": "not_observed"}
        assert _compute_scores(rows, _RAISE, bands) == {"specificity": 52.0}
        assert _compute_scores([], _RAISE, {}) == {}

    def test_a_raw_delta_outside_the_schema_counts_as_its_bound(self) -> None:
        """The stored output is raw model text; a runtime that ignores the
        schema can write any number there."""
        rows = [_npc_row(_obs("specificity", 40), _obs("composure", -40))]
        assert _compute_scores(rows, _RAISE) == {"specificity": 53.0, "composure": 47.0}
        assert _compute_scores(rows) == {"specificity": 53.0, "composure": 47.0}

    def test_without_a_rubric_every_written_id_is_scored_as_before(self) -> None:
        rows = [_npc_row(_obs("experience_gap", 3), _obs("Self Awareness", -1))]
        assert _compute_scores(rows) == {"experience_gap": 53.0, "self_awareness": 49.0}
        # Bands mean nothing without a rubric.
        assert _compute_scores(rows, None, {"experience_gap": "high"}) == _compute_scores(rows)


class TestOverallScore:
    def test_weighted_by_the_rubric(self) -> None:
        scores = {"business_case": 91.0, "specificity": 59.0, "composure": 25.0}
        # Renormalised over the scored dimensions: listening is not a zero.
        expected = (91 * 0.35 + 59 * 0.30 + 25 * 0.20) / 0.85
        assert _compute_overall_score(scores, _RAISE) == round(expected, 1)
        assert _compute_overall_score(scores) == round((91 + 59 + 25) / 3, 1)

    def test_unweighted_dimensions_share_equally(self) -> None:
        rubric = _rubric(("a", "A", None), ("b", "B", None))
        assert _compute_overall_score({"a": 80.0, "b": 40.0}, rubric) == 60.0
        mixed = _rubric(("a", "A", 0.5), ("b", "B", None))  # b's share is 1/2
        assert _compute_overall_score({"a": 80.0, "b": 40.0}, mixed) == 60.0

    def test_zero_weights_fall_back_to_the_mean(self) -> None:
        rubric = _rubric(("a", "A", 0.0), ("b", "B", 0.0))
        assert _compute_overall_score({"a": 80.0, "b": 40.0}, rubric) == 60.0

    def test_none_when_nothing_is_scored(self) -> None:
        assert _compute_overall_score({}, _RAISE) is None


class TestRubricBands:
    def _narrative(self, bands: Dict[str, str], fallback: bool = False) -> DebriefNarrative:
        return DebriefNarrative(
            summary="s", strengths=["a"], improvements=["b"], turning_points=[],
            used_fallback=fallback, dimension_bands=bands,
        )

    def test_keyed_by_the_rubric_in_its_order(self) -> None:
        narrative = self._narrative({"Composure": "low", "business_case": "high", "rapport": "high"})
        assert _rubric_bands(narrative, _RAISE) == {"business_case": "high", "composure": "low"}
        assert list(_rubric_bands(narrative, _RAISE)) == ["business_case", "composure"]

    def test_none_for_the_fallback_or_without_a_rubric(self) -> None:
        assert _rubric_bands(self._narrative({"business_case": "high"}, fallback=True), _RAISE) == {}
        assert _rubric_bands(self._narrative({"business_case": "high"}), None) == {}


# ---------------------------------------------------------------------------
# Hidden state stays out of the telemetry
# ---------------------------------------------------------------------------


def test_hidden_variables_are_left_out_of_the_state_arc() -> None:
    rows = [
        _Row(turn_number=0, role="npc_opening", content="Hi.", state_delta_json=None, created_at=""),
        _Row(turn_number=1, role="player", content="Hello.", state_delta_json=None, created_at=""),
        _Row(turn_number=2, role="npc", content="So.", state_delta_json=json.dumps(
            {"case_clarity": 5, "impression": 3}), created_at=""),
    ]
    final = {"case_clarity": 15, "impression": 48, "pressure": 25}
    hidden = _hidden_variables({"case_clarity": {"default": 10, "visibility": "hidden"}})
    assert hidden == {"case_clarity", "pressure"}  # pressure is a hidden baseline variable
    arc = compute_metrics(rows, final_state=final, hidden_variables=hidden)["state_arc"]
    assert arc == [{"turn_number": 1, "state": {"impression": 48}}]
    # Without the set, as before.
    full = compute_metrics(rows, final_state=final)["state_arc"]
    assert full[0]["state"] == {"case_clarity": 15, "impression": 48, "pressure": 25}


# ---------------------------------------------------------------------------
# End to end through the API
# ---------------------------------------------------------------------------


_RECORDED_LINES = [
    "Where does that number come from?",
    "And what did the migration save the team, in hours?",
    "Walk me through how you would measure that next quarter.",
]


class _RecordingRuntime(FakeChatRuntime):
    """A runtime that writes rubric notes and bands, and records every request.

    Its notes mix a rubric id, a spelling of one, and an id the rubric does
    not have, as a runtime that does not enforce the schema can.
    """

    def __init__(self, debrief_text: Optional[str] = None) -> None:
        self.requests: List[ChatRequest] = []
        self.debrief_text = debrief_text

    def chat_stream(self, request: ChatRequest) -> Any:
        self.requests.append(request)
        return self._respond(request)

    async def _respond(self, request: ChatRequest) -> AsyncGenerator:
        schema = request.json_schema or {}
        if "replay_suggestions" in (schema.get("properties") or {}):
            response: Optional[Dict[str, Any]] = {
                "summary": "You built a business case and named a figure.",
                "dimension_bands": {
                    "business_case": "high", "specificity": "medium",
                    "composure": "low", "listening": "not_observed",
                },
                "strengths": ["You cited outcomes at turn 1."],
                "improvements": ["Tie your figure to market data."],
                "turning_points": [{"turn_number": 1, "description": "Outcomes.", "impact": "positive"}],
                "replay_suggestions": ["Lead with the cost of not adjusting."],
            }
            text = self.debrief_text if self.debrief_text is not None else json.dumps(response)
            if self.debrief_text is not None:
                response = None
        else:
            # A different line each turn: the repetition guard (issue #580)
            # retries a reply that repeats the NPC's last line, which would
            # add a request these tests do not count.
            turn = len(self.turn_requests())
            response = {
                "npc_utterance": _RECORDED_LINES[(turn - 1) % len(_RECORDED_LINES)],
                "npc_emotion": "skeptical",
                "state_delta": {"evidence_strength": 5, "impression": 3},
                "event_flags": ["skeptical_of_claim"],
                "rubric_observations": [
                    {"rubric_id": "business_case", "observation": "Cited outcomes.", "score_delta": 3},
                    {"rubric_id": "Specificity", "observation": "Named a figure.", "score_delta": 2},
                    {"rubric_id": "confidence", "observation": "Invented id.", "score_delta": -3},
                ],
                "safety": {"status": "ok"},
                "session_control": {"continue_session": True},
            }
            text = json.dumps(response)
        for word in text.split():
            yield ChatToken(text=word + " ")
        yield ChatFinal(
            text=text, model_id="fake-small", input_tokens=10,
            output_tokens=len(text.split()), structured=response,
        )

    def turn_requests(self) -> List[ChatRequest]:
        return [r for r in self.requests if "replay_suggestions" not in (r.json_schema or {}).get("properties", {})]

    def debrief_requests(self) -> List[ChatRequest]:
        return [r for r in self.requests if "replay_suggestions" in (r.json_schema or {}).get("properties", {})]


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


def _play(
    app, scenario_id: str, runtime: _RecordingRuntime, turns: int = 2,
    stored: Optional[List[Dict[str, Any]]] = None,
):
    """Play ``turns`` turns of ``scenario_id`` on ``runtime``, end it, debrief it twice.

    ``stored``, when given, receives the debrief document as it was persisted.
    """
    from convsim_core.services.model_manager_service import set_active_config

    with TestClient(app) as client:
        # Unpinned sessions need a real-model selection (issue #473); the
        # recording runtime is swapped in after creation, so it is never called.
        set_active_config(app.state.db.connection(), runtime_id="llama_cpp", model_id="/tmp/model.gguf")
        res = client.post("/api/sessions", json={
            "scenario_id": scenario_id, "difficulty": "standard", "player_role_name": "Alex",
            "language": "en", "input_mode": "text-only", "tts_enabled": False,
            "show_state_meters": True, "save_transcript": True, "seed": None,
        })
        assert res.status_code == 201, res.text
        session_id = res.json()["session_id"]
        assert client.post(f"/api/sessions/{session_id}/start").status_code == 200
        app.state.runtime = runtime
        for n in range(turns):
            res = client.post(f"/api/sessions/{session_id}/turn", json={
                "content": f"My work cut onboarding time by a third ({n})."})
            assert res.status_code == 200, res.text
        client.post(f"/api/sessions/{session_id}/end")
        first = client.post(f"/api/sessions/{session_id}/debrief")
        again = client.post(f"/api/sessions/{session_id}/debrief")
        if stored is not None:
            row = app.state.db.connection().execute(
                "SELECT content_json FROM session_debriefs WHERE session_id = ?", (session_id,)
            ).fetchone()
            stored.append(json.loads(row[0]))
    assert first.status_code == 200, first.text
    assert again.status_code == 200, again.text
    return first.json(), again.json()


_RAISE_IDS = ["business_case", "specificity", "composure", "listening"]
_RAISE_NAMES = {
    "business_case": "Business Case", "specificity": "Specificity",
    "composure": "Composure", "listening": "Listening",
}


class TestAScenarioWithARubric:
    """ask_for_raise is not in the hardcoded catalog, so even the full app
    plays it from its pack, with raise_rubric."""

    def test_turns_are_sent_the_rubric_and_its_enum(self, app) -> None:
        runtime = _RecordingRuntime()
        _play(app, "ask_for_raise", runtime)
        turns = runtime.turn_requests()
        assert len(turns) == 2
        for request in turns:
            enum = request.json_schema["properties"]["rubric_observations"]["items"]["properties"]["rubric_id"]
            assert enum == {"type": "string", "enum": _RAISE_IDS}
            system = request.messages[0].content
            assert "--- LAYER:RUBRIC ---" in system
            assert (
                "  - business_case: Player cites specific outcomes they delivered, names the "
                "expanded scope of their current role relative to their job description or "
                "compensation band …"
            ) in system
            # The line keeps the clause that says what good looks like.
            assert (
                "  - listening: Player tracks what Diane's questions reveal about her underlying "
                "concern and adapts their argument to address that concern specifically rather "
                "than recycling earlier points\n"
            ) in system
            # The schema the prompt quotes is the one sent.
            assert json.dumps(request.json_schema, indent=2) in system

    def test_the_debrief_scores_the_rubric_only_from_bands_and_notes(self, app) -> None:
        body, again = _play(app, "ask_for_raise", _RecordingRuntime())
        assert body["used_fallback"] is False
        # Two turns: business_case +3 +3, specificity +2 +2 (a spelling of the
        # id), the invented "confidence" dropped; listening not_observed with
        # no notes, so absent rather than 50.
        assert body["scores"] == {
            "business_case": BAND_SCORES["high"] + 6,
            "specificity": BAND_SCORES["medium"] + 4,
            "composure": BAND_SCORES["low"],
        }
        assert list(body["scores"]) == ["business_case", "specificity", "composure"]
        assert body["overall_score"] == round((91 * 0.35 + 59 * 0.30 + 25 * 0.20) / 0.85, 1)
        assert body["dimension_names"] == _RAISE_NAMES
        assert body["dimension_bands"] == {
            "business_case": "high", "specificity": "medium",
            "composure": "low", "listening": "not_observed",
        }
        # The stored debrief answers the same.
        for key in ("scores", "overall_score", "dimension_names", "dimension_bands"):
            assert again[key] == body[key], key

    @pytest.mark.parametrize("debrief_text", [None, "not json at all"])
    def test_the_stored_debrief_matches_the_published_schema(self, app, debrief_text) -> None:
        # schemas/debrief.schema.json closes its top level, so a key the
        # engine stores and the schema does not declare fails validation.
        import jsonschema

        from convsim_core.schema_paths import get_schema

        stored: List[Dict[str, Any]] = []
        kwargs = {} if debrief_text is None else {"debrief_text": debrief_text}
        _play(app, "ask_for_raise", _RecordingRuntime(**kwargs), stored=stored)
        [doc] = stored
        jsonschema.validate(doc, get_schema("debrief.schema.json"))
        assert doc["dimension_names"] == _RAISE_NAMES

    def test_the_debrief_request_asks_for_the_bands(self, app) -> None:
        runtime = _RecordingRuntime()
        _play(app, "ask_for_raise", runtime)
        [request] = runtime.debrief_requests()
        bands = request.json_schema["properties"]["dimension_bands"]
        assert bands["required"] == _RAISE_IDS
        assert request.max_tokens == 1024
        system, user = request.messages[0].content, request.messages[1].content
        assert "- business_case: Business Case, weight 35%" in system
        assert "DIMENSION SCORES" not in system
        # The bands are judged from the player's lines (#580): the turn notes
        # are left out of the prompt, though they still move the scores.
        assert "Note on the player's line" not in user
        assert "Cited outcomes." not in user and "Named a figure." not in user
        assert "Invented id." not in user
        assert "  NPC signal: skeptical_of_claim" in user
        assert "[Rubric '" not in user and "[Flags]" not in user

    def test_hidden_variables_stay_out_of_the_telemetry(self, app) -> None:
        body, again = _play(app, "ask_for_raise", _RecordingRuntime())
        for snapshot in body["metrics"]["state_arc"]:
            assert "evidence_strength" not in snapshot["state"]
            assert "case_clarity" not in snapshot["state"]
            assert "pressure" not in snapshot["state"]
            assert "impression" in snapshot["state"]
        assert again["metrics"]["state_arc"] == body["metrics"]["state_arc"]

    def test_the_template_fallback_still_scores_the_rubric(self, app) -> None:
        body, _ = _play(app, "ask_for_raise", _RecordingRuntime(debrief_text="not json at all"))
        assert body["used_fallback"] is True
        assert body["scores"] == {"business_case": 56.0, "specificity": 54.0}
        assert body["overall_score"] == round((56 * 0.35 + 54 * 0.30) / 0.65, 1)
        assert body["dimension_names"] == _RAISE_NAMES
        assert body["dimension_bands"] == {}
        # The fallback text calls the dimension by its rubric name.
        assert all("business_case" not in s for s in body["strengths"] + body["improvements"])


class TestAScenarioWithNoRubric:
    """behavioral_interview plays its hardcoded catalog entry in the full app."""

    def test_plays_and_debriefs_as_before(self, app) -> None:
        runtime = _RecordingRuntime()
        body, _ = _play(app, "behavioral_interview", runtime)
        for request in runtime.turn_requests():
            assert request.json_schema == NPC_TURN_OUTPUT_SCHEMA
            assert "--- LAYER:RUBRIC ---" not in request.messages[0].content
        [debrief] = runtime.debrief_requests()
        assert debrief.json_schema == DEBRIEF_NARRATIVE_SCHEMA
        assert "DIMENSION SCORES" in debrief.messages[0].content
        # Every written id is scored, spellings folded, from 50.
        assert body["scores"] == {"business_case": 56.0, "specificity": 54.0, "confidence": 44.0}
        assert body["overall_score"] == round((56 + 54 + 44) / 3, 1)
        assert body["dimension_names"] == {}
        assert body["dimension_bands"] == {}
        assert body["used_fallback"] is False
