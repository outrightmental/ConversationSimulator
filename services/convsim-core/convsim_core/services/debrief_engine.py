# SPDX-License-Identifier: Apache-2.0
"""Debrief generation engine.

Processing steps:
  1. Load all turns + raw LLM output for the session from the database.
  2. Tally the per-turn rubric_observations by dimension.
  3. Identify key turning points from state changes, event flags, safety events.
  4. Build a debrief prompt with scenario context, the rubric, and the transcript.
  5. Call the ChatRuntime and parse/repair/fallback the debrief narrative JSON.
  6. Score each dimension, and the overall weighted score (see below).
  7. Assemble and persist the full debrief document.
  8. Transition session flow_state to DebriefReady (or Error on failure).

Scoring (issue #578). A scenario with a rubric is scored on the rubric's
dimensions only, labelled with their names, and its overall score weights them
by the rubric's weights. The debrief model places each dimension in one of the
rubric's bands; a band sets the dimension's score (BAND_SCORES: low 25, medium
55, high 85, one in each colour zone of the scorecard), and the turn-by-turn
notes move it by their net score_delta, at most BAND_ADJUST_MAX either way, so
a band always decides the zone. A dimension with no band (the template
fallback, a model that gave none, or "not_observed") is scored as before, 50
plus the net of its notes; one with neither is left off the scorecard. Before
this, every score was 50 plus deltas of 1-3 per note, so a short session could
not leave roughly 44-56 and a good run read like a weak one. A scenario with no
rubric (the hardcoded catalog) keeps the old scoring and a plain mean.

Language rules (enforced via DEBRIEF_SYSTEM_PREAMBLE):
  - No therapy, clinical assessment, or mental-health advice.
  - No real-world performance guarantees.
  - Evidence cited by turn number and short quotes — no invented quotes, and
    nothing the NPC said credited to the player.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
from dataclasses import dataclass, field, fields as dataclass_fields
from datetime import datetime, timezone
from typing import Any, Collection, Dict, List, Optional, Set

from convsim_prompt import (
    DebriefNarrative,
    DebriefTurnRecord,
    RubricIdMatcher,
    build_debrief_narrative_schema,
    compose_debrief_prompt,
    normalize_dimension_id,
    parse_debrief_narrative,
)
from convsim_prompt.debrief_composer import DebriefComposerInput
from convsim_prompt.types import ScenarioData, ScenarioRubric

from convsim_core.runtime.base import ChatRuntime
from convsim_core.runtime.types import ChatFinal, ChatMessage, ChatRequest, ChatToken
from convsim_core.scenario_state import build_variable_defs, hidden_variable_names
from convsim_core.services.model_registry_service import active_model_sampling

logger = logging.getLogger(__name__)

# Neutral baseline for rubric dimension scores (0–100 scale).
_SCORE_BASELINE = 50.0
_SCORE_MIN = 0.0
_SCORE_MAX = 100.0

# A note's score_delta, as the turn schema bounds it. The debrief reads the
# raw model text, which a runtime that ignores the schema can put anything in.
_NOTE_DELTA_MIN = -3
_NOTE_DELTA_MAX = 3

#: The score each rubric band sets (issue #578): one in each colour zone of
#: the scorecard (red below 40, orange to 69, green from 70; Debrief.tsx).
BAND_SCORES: Dict[str, float] = {"low": 25.0, "medium": 55.0, "high": 85.0}
#: How far the turn-by-turn notes can move a banded dimension, either way.
#: Twelve keeps every band inside its zone (25±12, 55±12, 85-12).
BAND_ADJUST_MAX = 12.0

# The debrief's output budget. A reply cut off at it is invalid JSON, and the
# debrief falls back to the template. The 512 ChatRequest default left almost
# no headroom over the narrative alone; 1024 did not fit a reply that fills
# the narrative schema's lists (``maxItems``) with the missed opportunities
# and slips the debrief now lists (issue #580): every list full, at the
# longest each ran in the D-05 replay's debriefs, came to ~1270 tokens on the
# starter model. The longest session's prompt leaves 1536 room in its 8192
# context (tests/test_debrief_budget.py).
_DEBRIEF_MAX_TOKENS = 1536

# Single-token filler / disfluency markers detected in voice-mode transcripts
# (STT tokens).  Deliberately excludes ordinary content words such as "i",
# "you", "so", or "okay": those appear in nearly every utterance and counting
# them would swamp the metric with false positives.
_FILLER_WORDS: frozenset = frozenset([
    "um", "umm", "uh", "uhm", "uhh", "erm", "err", "er", "ah", "hmm",
    "like", "basically", "literally", "actually",
])

# Multi-word filler phrases counted as a single filler when their tokens appear
# consecutively (e.g. "you know", "i mean").  Matching the phrase avoids
# counting the individual common words on their own.
_FILLER_PHRASES: tuple = (
    ("you", "know"),
    ("i", "mean"),
    ("sort", "of"),
    ("kind", "of"),
)

# First words (lowercased) that introduce an open-ended question.
_OPEN_QUESTION_STARTERS: frozenset = frozenset([
    "what", "why", "how", "who", "when", "where", "which",
    "tell", "describe", "explain", "elaborate", "share",
    "could", "can", "would", "walk",
])

# Sanity ceiling for a single NPC latency measurement (5 minutes).
_LATENCY_MAX_MS = 300_000.0


@dataclass
class DebriefResult:
    session_id: str
    scenario_id: str
    pack_id: Optional[str]
    outcome: str
    total_turns: int
    scores: Dict[str, float]
    overall_score: Optional[float]
    summary: str
    strengths: List[str]
    improvements: List[str]
    missed_opportunities: List[str]
    turning_points: List[Dict[str, Any]]
    replay_suggestions: List[str]
    npc_final_state: Dict[str, int]
    generated_at: str
    used_fallback: bool = False
    metrics: Dict[str, Any] = field(default_factory=dict)
    # Rubric dimension id → the rubric's name for it, for every dimension of
    # the scenario's rubric (issue #578); empty for a scenario with none.
    dimension_names: Dict[str, str] = field(default_factory=dict)
    # Rubric dimension id → the band the debrief placed it in.
    dimension_bands: Dict[str, str] = field(default_factory=dict)


def _count_words(text: str) -> int:
    return len(text.split()) if text else 0


def _parse_iso_timestamp(ts: str) -> Optional[float]:
    """Return a Unix-epoch float from an ISO 8601 string, or None on error."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def compute_metrics(
    all_turns: List[sqlite3.Row],
    source_mode: str = "text-only",
    final_state: Optional[Dict[str, int]] = None,
    interruption_count: int = 0,
    hidden_variables: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Compute session telemetry metrics from stored transcript rows.

    Pure function — deterministic given the same rows.  Does not read from the
    database or call any external service.

    ``hidden_variables`` are left out of the state arc: the debrief's
    telemetry panel draws one meter per variable in it, and a variable the
    scenario marks ``visibility: hidden`` is never shown during play. It sat
    in the panel next to the scorecard's same-named dimension (issue #580,
    P6: "case clarity 48" beside a hidden ``case_clarity`` of 10).

    Args:
        all_turns: Ordered rows from turn_session_turns for one session.
        source_mode: The session input_mode ("text-only", "push-to-talk", "hands-free").
        final_state: The session's final (clamped) state variable values. Used to
            anchor the state arc to true meter values: stored deltas are the
            clamped per-turn change, so the true starting value is
            ``final_state - sum(deltas)``. When omitted, the arc is relative to
            zero (deltas only).
    """
    player_turns = [t for t in all_turns if t["role"] == "player"]
    all_npc_speech = [t for t in all_turns if t["role"] in ("npc", "npc_opening")]

    # --- Talk ratio and words per turn ---
    player_word_total = sum(_count_words(t["content"] or "") for t in player_turns)
    npc_word_total = sum(_count_words(t["content"] or "") for t in all_npc_speech)
    grand_total = player_word_total + npc_word_total
    talk_ratio = round(player_word_total / grand_total, 3) if grand_total > 0 else 0.0
    words_per_turn_player = (
        round(player_word_total / len(player_turns), 1) if player_turns else 0.0
    )
    words_per_turn_npc = (
        round(npc_word_total / len(all_npc_speech), 1) if all_npc_speech else 0.0
    )

    # --- Question counts (heuristic: sentence ends with "?") ---
    open_questions = 0
    closed_questions = 0
    for turn in player_turns:
        content = turn["content"] or ""
        # Split on whitespace following a "?" so multi-question turns are handled.
        fragments = re.split(r"(?<=[?])\s+", content)
        for fragment in fragments:
            fragment = fragment.strip()
            if not fragment.endswith("?"):
                continue
            first_word = fragment.split()[0].lower() if fragment.split() else ""
            if first_word in _OPEN_QUESTION_STARTERS:
                open_questions += 1
            else:
                closed_questions += 1

    # --- Filler word count (voice sessions only) ---
    filler_word_count = 0
    if source_mode in ("push-to-talk", "hands-free"):
        for turn in player_turns:
            tokens = re.findall(r"\b\w+\b", (turn["content"] or "").lower())
            # Consume tokens left to right so a phrase match doesn't also count
            # its constituent single-token fillers.
            i = 0
            while i < len(tokens):
                phrase_len = 0
                for phrase in _FILLER_PHRASES:
                    if tuple(tokens[i:i + len(phrase)]) == phrase:
                        phrase_len = len(phrase)
                        break
                if phrase_len:
                    filler_word_count += 1
                    i += phrase_len
                    continue
                if tokens[i] in _FILLER_WORDS:
                    filler_word_count += 1
                i += 1

    # --- Response latency (player turn submitted → NPC turn persisted) ---
    # Turn numbering: player turn N is at row turn_number=2N-1, NPC at 2N.
    ts_by_num: Dict[int, str] = {t["turn_number"]: t["created_at"] for t in all_turns}
    latencies_ms: List[float] = []
    for p_turn in player_turns:
        p_num = p_turn["turn_number"]
        npc_ts_raw = ts_by_num.get(p_num + 1)
        p_ts_raw = p_turn["created_at"]
        if not npc_ts_raw or not p_ts_raw:
            continue
        p_time = _parse_iso_timestamp(p_ts_raw)
        n_time = _parse_iso_timestamp(npc_ts_raw)
        if p_time is None or n_time is None:
            continue
        delta_ms = (n_time - p_time) * 1000.0
        if 0 <= delta_ms < _LATENCY_MAX_MS:
            latencies_ms.append(delta_ms)

    p50_ms: Optional[int] = None
    p95_ms: Optional[int] = None
    if latencies_ms:
        sorted_lat = sorted(latencies_ms)
        n = len(sorted_lat)
        p50_ms = round(sorted_lat[n // 2])
        p95_idx = min(int(0.95 * n + 0.5), n - 1)
        p95_ms = round(sorted_lat[p95_idx])

    # --- State arc: cumulative state after each NPC response turn ---
    # state_delta_json stores the *actual* (clamped) per-turn change to each
    # variable, not the raw meter value.  Scenario variables start from their
    # defined defaults (e.g. 50), so summing deltas from zero would understate
    # real meter values and could even go negative.  We anchor the running state
    # to the true initial values, derived as ``final_state - sum(deltas)``, so
    # each snapshot reproduces the exact clamped meter value at that turn.
    parsed_deltas: List[Dict[str, int]] = []
    total_deltas: Dict[str, int] = {}
    for turn in all_turns:
        delta_clean: Dict[str, int] = {}
        if turn["state_delta_json"]:
            try:
                raw = json.loads(turn["state_delta_json"])
                if isinstance(raw, dict):
                    for var_name, var_delta in raw.items():
                        if isinstance(var_delta, (int, float)):
                            delta_clean[var_name] = int(var_delta)
                            total_deltas[var_name] = (
                                total_deltas.get(var_name, 0) + int(var_delta)
                            )
            except json.JSONDecodeError:
                pass
        parsed_deltas.append(delta_clean)

    running_state: Dict[str, int] = {}
    if final_state:
        for var_name, final_val in final_state.items():
            running_state[var_name] = int(final_val) - total_deltas.get(var_name, 0)

    hidden = hidden_variables or set()
    state_arc: List[Dict[str, Any]] = []
    for turn, delta_clean in zip(all_turns, parsed_deltas):
        for var_name, var_delta in delta_clean.items():
            running_state[var_name] = running_state.get(var_name, 0) + var_delta
        if turn["role"] == "npc":
            # Whole turns, like turning_points and the transcript labels, so one
            # debrief carries a single turn numbering (issue #501 §4).
            state_arc.append({
                "turn_number": whole_turn_of(turn["turn_number"]),
                "state": {k: v for k, v in running_state.items() if k not in hidden},
            })

    return {
        "metrics_version": "1",
        "talk_ratio": talk_ratio,
        "words_per_turn_player": words_per_turn_player,
        "words_per_turn_npc": words_per_turn_npc,
        "open_questions": open_questions,
        "closed_questions": closed_questions,
        "filler_word_count": filler_word_count,
        "interruption_count": interruption_count,
        "response_latency_p50_ms": p50_ms,
        "response_latency_p95_ms": p95_ms,
        "state_arc": state_arc,
    }


def _parse_rubric_observations(raw_output_json: Optional[str]) -> List[Dict[str, Any]]:
    """Extract rubric_observations list from a stored raw LLM output string."""
    if not raw_output_json:
        return []
    try:
        data = json.loads(raw_output_json)
        obs = data.get("rubric_observations")
        if isinstance(obs, list):
            return obs
    except (json.JSONDecodeError, AttributeError):
        pass
    return []


@dataclass
class _DimensionTally:
    """The turn-by-turn notes on one dimension: how many, and their net score_delta."""
    notes: int = 0
    net: int = 0


def _tally_observations(
    npc_turns: List[sqlite3.Row],
    rubric: Optional[ScenarioRubric] = None,
) -> Dict[str, _DimensionTally]:
    """Group the NPC turns' rubric_observations by dimension.

    Spellings of one id are counted together (normalize_dimension_id). With a
    rubric, an observation counts only under the rubric dimension its id (or
    the dimension's name) stands for, and every other observation is dropped:
    the turn schema's enum keeps a schema-enforcing runtime to the rubric's
    ids, and this keeps the rest to them. Each score_delta is clamped to the
    schema's [-3, 3]: the stored output is the model's raw text.
    """
    matcher = RubricIdMatcher.for_rubric(rubric) if rubric is not None else None
    tallies: Dict[str, _DimensionTally] = {}
    for turn in npc_turns:
        for obs in _parse_rubric_observations(turn["raw_output_json"]):
            if not isinstance(obs, dict):
                continue
            written = obs.get("rubric_id")
            if not isinstance(written, str) or not written:
                continue
            dim_id = matcher.match(written) if matcher is not None else normalize_dimension_id(written)
            if not dim_id:
                continue
            tally = tallies.setdefault(dim_id, _DimensionTally())
            tally.notes += 1
            score_delta = obs.get("score_delta")
            if isinstance(score_delta, int) and not isinstance(score_delta, bool):
                tally.net += max(_NOTE_DELTA_MIN, min(_NOTE_DELTA_MAX, score_delta))
    return tallies


def _clamp_score(score: float) -> float:
    return max(_SCORE_MIN, min(_SCORE_MAX, score))


def _compute_scores(
    npc_turns: List[sqlite3.Row],
    rubric: Optional[ScenarioRubric] = None,
    bands: Optional[Dict[str, str]] = None,
) -> Dict[str, float]:
    """Score each dimension from the turns' notes and, with a rubric, its band.

    Without a rubric, as before: every dimension that has a note scores 50
    plus the net score_delta of its notes, clamped to [0, 100].

    With a rubric, only its dimensions, in its order. A dimension the debrief
    placed in a band (``bands``, id → low / medium / high) scores
    BAND_SCORES[band] plus its notes' net, the net capped at ±BAND_ADJUST_MAX.
    A dimension with no band (none given, or "not_observed") falls back to 50
    plus its net when it has notes, and is left out when it has none: a
    dimension nothing was said about is absent, not a 50.
    """
    tallies = _tally_observations(npc_turns, rubric)
    if rubric is None:
        return {
            dim_id: _clamp_score(_SCORE_BASELINE + tally.net)
            for dim_id, tally in tallies.items()
        }
    bands = bands or {}
    scores: Dict[str, float] = {}
    for dimension in rubric.dimensions:
        tally = tallies.get(dimension.id)
        band_score = BAND_SCORES.get(bands.get(dimension.id, ""))
        if band_score is not None:
            net = tally.net if tally is not None else 0
            adjust = max(-BAND_ADJUST_MAX, min(BAND_ADJUST_MAX, float(net)))
            scores[dimension.id] = _clamp_score(band_score + adjust)
        elif tally is not None:
            scores[dimension.id] = _clamp_score(_SCORE_BASELINE + tally.net)
    return scores


def _dimension_weights(rubric: ScenarioRubric) -> Dict[str, float]:
    """Each dimension's weight: the authored one, or an equal share when it has none."""
    share = 1.0 / len(rubric.dimensions) if rubric.dimensions else 0.0
    return {
        d.id: (d.weight if d.weight is not None else share)
        for d in rubric.dimensions
    }


def _compute_overall_score(
    scores: Dict[str, float],
    rubric: Optional[ScenarioRubric] = None,
) -> Optional[float]:
    """The overall score, or None if no dimension was scored.

    With a rubric, the mean of the scored dimensions weighted by the rubric's
    weights, renormalised over the dimensions that were scored (a dimension
    left off the scorecard does not count as a zero). Without a rubric, or
    when the scored dimensions' weights sum to zero, the plain mean.
    """
    if not scores:
        return None
    if rubric is not None:
        weights = _dimension_weights(rubric)
        total = sum(weights.get(dim_id, 0.0) for dim_id in scores)
        if total > 0:
            weighted = sum(score * weights.get(dim_id, 0.0) for dim_id, score in scores.items())
            return round(weighted / total, 1)
    return round(sum(scores.values()) / len(scores), 1)


def _rubric_bands(
    narrative: DebriefNarrative,
    rubric: Optional[ScenarioRubric],
) -> Dict[str, str]:
    """The debrief's bands for the rubric's dimensions, keyed by the rubric's ids.

    The template fallback has none. A key that is a spelling of a dimension's
    id or name counts for that dimension; any other key is dropped.
    """
    if rubric is None or narrative.used_fallback:
        return {}
    matcher = RubricIdMatcher.for_rubric(rubric)
    bands: Dict[str, str] = {}
    for written, band in narrative.dimension_bands.items():
        dim_id = matcher.match(written)
        if dim_id is not None:
            bands.setdefault(dim_id, band)
    return {d.id: bands[d.id] for d in rubric.dimensions if d.id in bands}


def _hidden_variables(
    state_variable_overrides: Optional[Dict[str, Any]],
    played_variables: Optional[Collection[str]] = None,
) -> Set[str]:
    """The state variables the scenario hides from the player.

    Those it marks hidden and, when ``played_variables`` names any, every
    variable outside them (issue #580): the meters during play leave those
    out, because the turns cannot move them.
    """
    try:
        defs = build_variable_defs(state_variable_overrides)
    except (TypeError, ValueError, AttributeError):
        return set()
    return hidden_variable_names(defs, played_variables)


def whole_turn_of(row_turn_number: int) -> int:
    """Map a transcript row number to the whole turn it belongs to.

    Rows are stored as the opening at 0 and then player ``2n-1`` / NPC ``2n``
    for whole turn ``n``. A whole turn is one player message plus the reply to
    it (issue #501 §4), which is the unit ``turn_count`` counts, that
    ``duration.max_turns`` is measured in, and that the transcript labels — so
    it is the only number a debrief may quote at a player. The opening belongs
    to no turn and maps to 0.
    """
    return (row_turn_number + 1) // 2


def _identify_key_turns(
    npc_turns: List[sqlite3.Row],
) -> List[Dict[str, Any]]:
    """Identify turns with significant state changes or notable events.

    Returns a list of dicts ready for fallback narrative generation,
    each containing turn_number, description, and impact.

    ``turn_number`` is a whole turn, not the NPC row's stored number: these
    reach the player as "#3" next to a transcript labelled "Turn 3", and before
    issue #501 the two counted differently.
    """
    key: List[Dict[str, Any]] = []

    for turn in npc_turns:
        turn_number = whole_turn_of(turn["turn_number"])
        state_delta: Dict[str, int] = {}
        if turn["state_delta_json"]:
            try:
                state_delta = json.loads(turn["state_delta_json"])
            except json.JSONDecodeError:
                pass

        event_flags: List[str] = []
        if turn["event_flags_json"]:
            try:
                event_flags = json.loads(turn["event_flags_json"])
            except json.JSONDecodeError:
                pass

        safety_status = "ok"
        if turn["safety_json"]:
            try:
                safety_status = json.loads(turn["safety_json"]).get("status", "ok")
            except (json.JSONDecodeError, AttributeError):
                pass

        # Significant state change: any single variable changed by ≥8 points.
        big_changes = {k: v for k, v in state_delta.items() if abs(v) >= 8}
        if big_changes:
            direction = "positive" if sum(big_changes.values()) > 0 else "negative"
            vars_str = ", ".join(
                f"{k} {v:+d}" for k, v in sorted(big_changes.items())
            )
            key.append({
                "turn_number": turn_number,
                "description": f"Significant state shift at turn {turn_number}: {vars_str}.",
                "impact": direction,
            })
        elif safety_status in ("redirect", "stop"):
            key.append({
                "turn_number": turn_number,
                "description": f"Safety {safety_status} triggered at turn {turn_number}.",
                "impact": "negative",
            })
        elif event_flags:
            key.append({
                "turn_number": turn_number,
                "description": (
                    f"Event flags raised at turn {turn_number}: {', '.join(event_flags)}."
                ),
                "impact": "neutral",
            })

    return key


def _build_debrief_turn_records(
    all_turns: List[sqlite3.Row],
) -> List[DebriefTurnRecord]:
    """Convert DB rows into DebriefTurnRecord objects for the prompt composer.

    Numbered in whole turns, so both halves of an exchange are "[Turn 3]" in
    the prompt and a turning point the model cites is a number the player can
    find in the transcript (issue #501 §4).
    """
    records: List[DebriefTurnRecord] = []
    for turn in all_turns:
        obs = _parse_rubric_observations(turn["raw_output_json"])
        state_delta: Dict[str, int] = {}
        if turn["state_delta_json"]:
            try:
                state_delta = json.loads(turn["state_delta_json"])
            except json.JSONDecodeError:
                pass
        event_flags: List[str] = []
        if turn["event_flags_json"]:
            try:
                event_flags = json.loads(turn["event_flags_json"])
            except json.JSONDecodeError:
                pass
        records.append(DebriefTurnRecord(
            turn_number=whole_turn_of(turn["turn_number"]),
            role=turn["role"],
            content=turn["content"],
            rubric_observations=obs,
            state_delta=state_delta,
            event_flags=event_flags,
        ))
    return records


async def _collect_runtime_output(runtime: ChatRuntime, request: ChatRequest) -> str:
    raw_text = ""
    async for chunk in runtime.chat_stream(request):
        if isinstance(chunk, ChatFinal):
            raw_text = chunk.text
            break
        elif isinstance(chunk, ChatToken):
            raw_text += chunk.text
    return raw_text


async def generate_debrief(
    session_row: sqlite3.Row,
    conn: sqlite3.Connection,
    runtime: ChatRuntime,
    scenario_data: ScenarioData,
    *,
    state_variable_overrides: Optional[Dict[str, Any]] = None,
    played_variables: Optional[Collection[str]] = None,
    config: Any = None,
) -> DebriefResult:
    """Generate, persist, and return a debrief for a completed session.

    Transitions the session through DebriefGenerating → DebriefReady/Error.
    Always returns a DebriefResult (falls back to template narrative on LLM error).

    ``scenario_data.rubric``, when the scenario has one, decides what is
    scored (see the module docstring). ``state_variable_overrides`` is the
    scenario's ``state.variables`` and ``played_variables`` the variables it
    plays (``ScenarioInfo.played_variables``): the telemetry's state arc
    leaves out the ones it hides and, when it plays any, every other one,
    the same set the meters left out during play. ``config`` is the service
    config, which picks the model the debrief is sampled for, as for the
    session's turns (see ``process_turn``).
    """
    session_id: str = session_row["session_id"]
    scenario_id: str = session_row["scenario_id"]
    setup: Dict[str, Any] = json.loads(session_row["setup_json"] or "{}")
    pack_id: Optional[str] = setup.get("pack_id")
    difficulty_preset: Optional[str] = setup.get("difficulty")
    outcome: str = session_row["ending_type"] or "player_exit"
    final_state: Dict[str, int] = json.loads(session_row["state_vars_json"] or "{}")
    total_turns: int = int(session_row["turn_count"])
    now = datetime.now(timezone.utc).isoformat()

    # Idempotent: a debrief already exists (double-click, remount, retry after a
    # dropped response) → return it instead of violating the UNIQUE constraint
    # with a 500. Generation is expensive and the content is deterministic per
    # session end, so "generate" is naturally "generate-or-get".
    existing = conn.execute(
        "SELECT content_json FROM session_debriefs WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if existing is not None:
        try:
            cached = json.loads(existing["content_json"])
            # content_json is a superset of DebriefResult (schema_version,
            # difficulty_preset, …) and may omit optional fields — filter and
            # default rather than trusting an exact match.
            allowed = {f.name for f in dataclass_fields(DebriefResult)}
            data = {k: v for k, v in cached.items() if k in allowed}
            data.setdefault("pack_id", None)
            data.setdefault("used_fallback", False)
            data.setdefault("metrics", {})
            result = DebriefResult(**data)
            conn.execute(
                "UPDATE turn_sessions SET flow_state = 'DebriefReady' WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()
            return result
        except (TypeError, ValueError, KeyError):
            # Corrupt cached row — fall through and regenerate over it.
            conn.execute(
                "DELETE FROM session_debriefs WHERE session_id = ?", (session_id,)
            )
            conn.commit()

    # Transition to DebriefGenerating.
    conn.execute(
        "UPDATE turn_sessions SET flow_state = 'DebriefGenerating' WHERE session_id = ?",
        (session_id,),
    )
    conn.commit()

    try:
        # Load all turns for transcript.
        all_turn_rows = conn.execute(
            "SELECT turn_number, role, content, emotion, state_delta_json, "
            "event_flags_json, safety_json, raw_output_json, source_mode, "
            "barged_in, created_at "
            "FROM turn_session_turns WHERE session_id = ? ORDER BY turn_number ASC",
            (session_id,),
        ).fetchall()

        # NPC turns hold raw_output_json with rubric_observations.
        npc_turn_rows = [r for r in all_turn_rows if r["role"] == "npc"]

        # Count player turns where the player barges in on NPC TTS playback.
        barge_in_count = sum(
            1 for r in all_turn_rows
            if r["role"] == "player" and r["barged_in"]
        )

        # Scores from the turns' notes alone: the prompt's scores for a
        # scenario with no rubric, and the template fallback's. A rubric's
        # bands, once the model has placed them, are added below.
        rubric = scenario_data.rubric
        dimension_names = {d.id: d.name for d in rubric.dimensions} if rubric else {}
        turn_scores = _compute_scores(npc_turn_rows, rubric)

        # Compute telemetry metrics (pure, deterministic over this transcript).
        source_mode = setup.get("input_mode", "text-only")
        metrics = compute_metrics(
            all_turn_rows,
            source_mode=source_mode,
            final_state=final_state,
            interruption_count=barge_in_count,
            hidden_variables=_hidden_variables(state_variable_overrides, played_variables),
        )

        # Identify key turning points for fallback and for the LLM.
        key_turns = _identify_key_turns(npc_turn_rows)

        # Build prompt.
        turn_records = _build_debrief_turn_records(all_turn_rows)
        composer_input = DebriefComposerInput(
            session_id=session_id,
            scenario_id=scenario_id,
            scenario_title=scenario_data.title,
            player_role_label=scenario_data.player_role_label,
            outcome=outcome,
            total_turns=total_turns,
            final_state=final_state,
            scores=turn_scores,
            turns=turn_records,
            rubric_dimension_names=dimension_names,
            pack_id=pack_id,
            difficulty_preset=difficulty_preset,
            rubric_dimensions=list(rubric.dimensions) if rubric else [],
            player_visible_goals=list(scenario_data.player_visible_goals),
            npc_name=scenario_data.npc.display_name,
        )
        prompt = compose_debrief_prompt(composer_input)

        # Call runtime.
        messages = [
            ChatMessage(role="system", content=prompt.system_prompt),
            ChatMessage(role="user", content=prompt.user_prompt),
        ]
        # Same model, same sampling as the session's turns: the registry's
        # temperature and top_p when its entry declares them (issue #580).
        # The schema asks for a band per rubric dimension when there is a
        # rubric (issue #578); the prompt quotes the same schema.
        request = ChatRequest(
            messages=messages,
            json_schema=build_debrief_narrative_schema(
                rubric_ids=rubric.dimension_ids if rubric else None,
            ),
            max_tokens=_DEBRIEF_MAX_TOKENS,
            **active_model_sampling(conn, runtime.id, config).request_fields(),
        )
        logger.debug(
            "Calling runtime %s for debrief of session %s (~%d tokens)",
            runtime.id, session_id, prompt.estimated_token_count,
        )
        raw_text = await _collect_runtime_output(runtime, request)

        # Whole turns actually played in this session. The opening maps to 0 and
        # is excluded: a turning point has to point at an exchange the player
        # can be shown, and the transcript labels the opening rather than
        # numbering it (issue #501 §4).
        stored_turn_numbers = {
            n for n in (whole_turn_of(r["turn_number"]) for r in all_turn_rows) if n > 0
        }

        # Validate / repair / fallback.
        narrative: DebriefNarrative = parse_debrief_narrative(
            raw_text,
            fallback_outcome=outcome,
            fallback_scores=turn_scores,
            fallback_key_turns=key_turns,
            fallback_dimension_names=dimension_names,
            fallback_overall_score=_compute_overall_score(turn_scores, rubric),
        )

        # The final scores: the rubric's bands, as the model placed them, plus
        # the turns' notes (see _compute_scores). With no rubric, or with the
        # template fallback, there are no bands and these are the turn scores.
        dimension_bands = _rubric_bands(narrative, rubric)
        scores = _compute_scores(npc_turn_rows, rubric, dimension_bands)
        overall_score = _compute_overall_score(scores, rubric)

        # Drop any turning points that reference turn numbers not in the transcript.
        # This prevents invented evidence regardless of whether we got LLM or fallback output.
        valid_turning_points = [
            tp for tp in narrative.turning_points
            if tp.turn_number in stored_turn_numbers
        ]
        if len(valid_turning_points) < len(narrative.turning_points):
            dropped = len(narrative.turning_points) - len(valid_turning_points)
            logger.warning(
                "Dropped %d turning point(s) with invalid turn numbers for session %s",
                dropped, session_id,
            )
            narrative.turning_points = valid_turning_points

        if narrative.used_fallback:
            logger.warning("Debrief for session %s used fallback narrative", session_id)

        # Assemble full debrief document.
        debrief_doc: Dict[str, Any] = {
            "schema_version": "0.1",
            "session_id": session_id,
            "scenario_id": scenario_id,
            "outcome": outcome,
            "total_turns": total_turns,
            "scores": {k: round(v, 1) for k, v in scores.items()},
            "overall_score": overall_score,
            "summary": narrative.summary,
            "strengths": narrative.strengths,
            "improvements": narrative.improvements,
            "missed_opportunities": narrative.missed_opportunities,
            "turning_points": [
                {
                    "turn_number": tp.turn_number,
                    "description": tp.description,
                    "impact": tp.impact,
                }
                for tp in narrative.turning_points
            ],
            "replay_suggestions": narrative.replay_suggestions,
            "npc_final_state": final_state,
            "generated_at": now,
            "used_fallback": narrative.used_fallback,
            "metrics": metrics,
            "dimension_names": dimension_names,
            "dimension_bands": dimension_bands,
        }
        if pack_id:
            debrief_doc["pack_id"] = pack_id
        if difficulty_preset:
            debrief_doc["difficulty_preset"] = difficulty_preset

        # Persist and transition to DebriefReady. ON CONFLICT DO NOTHING makes
        # concurrent generation attempts race-safe: the pre-generation
        # existence check above covers sequential retries, but two overlapping
        # requests (double-click, remount) both pass it and both generate —
        # the second INSERT must not blow up the request with a 500.
        with conn:
            conn.execute(
                "INSERT INTO session_debriefs (session_id, content_json, metrics_json, generated_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(session_id) DO NOTHING",
                (session_id, json.dumps(debrief_doc), json.dumps(metrics), now),
            )
            # Backfill ended_at for sessions that reached a terminal state
            # mid-turn (safety_stop/timeout/player_exit) without an explicit
            # /end call, so the Logbook can measure their practice time.
            conn.execute(
                "UPDATE turn_sessions SET flow_state = 'DebriefReady', "
                "ended_at = COALESCE(ended_at, datetime('now')) WHERE session_id = ?",
                (session_id,),
            )

        logger.debug("Debrief persisted for session %s (fallback=%s)", session_id, narrative.used_fallback)

        return DebriefResult(
            session_id=session_id,
            scenario_id=scenario_id,
            pack_id=pack_id,
            outcome=outcome,
            total_turns=total_turns,
            scores={k: round(v, 1) for k, v in scores.items()},
            overall_score=overall_score,
            summary=narrative.summary,
            strengths=narrative.strengths,
            improvements=narrative.improvements,
            missed_opportunities=narrative.missed_opportunities,
            turning_points=debrief_doc["turning_points"],
            replay_suggestions=narrative.replay_suggestions,
            npc_final_state=final_state,
            generated_at=now,
            used_fallback=narrative.used_fallback,
            metrics=metrics,
            dimension_names=dimension_names,
            dimension_bands=dimension_bands,
        )

    except Exception as exc:
        logger.error("Debrief generation failed for session %s: %s", session_id, exc)
        conn.execute(
            "UPDATE turn_sessions SET flow_state = 'Error' WHERE session_id = ?",
            (session_id,),
        )
        conn.commit()
        raise
