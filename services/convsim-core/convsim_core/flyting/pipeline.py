# SPDX-License-Identifier: Apache-2.0
"""End-to-end flyting volley pipeline: the turn loop for ``mode: flyting``.

One player submission runs:

  1. Stages 0-2 (deterministic: gates, craft, novelty) — no model.
  2. Stage 3: exactly one judge call, temperature 0, JSON-schema constrained.
     Unusable output gets exactly one retry, then the volley is scored
     mechanically and flagged ``judge_unavailable``.
  3. Stage 4: composition, with the heat multiplier that was in force when the
     volley arrived.
  4. The opponent: a counter-volley in a bout (scored by the same pipeline, with
     its numbers shown) or a non-countering reaction in batting practice.
  5. Momentum or heat and whiffs, then persistence: the two turns land in
     ``turn_session_turns`` like any other conversation, the scorecards land in
     ``flyting_volleys``, and the run state is written back to the session row.

The session row is an ordinary ``turn_sessions`` row, so transcripts, exports,
branch sessions, and deletion all work on a flyting run without special cases.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from convsim_prompt import (
    FLYTING_JUDGE_OUTPUT_SCHEMA,
    JUDGE_REPAIR_PROMPT,
    JudgeEvent,
    NpcData,
    VolleyJudgment,
    compose_volley_judge_prompt,
    parse_volley_judgment,
)

from convsim_core.flyting.config import PlayFormat
from convsim_core.flyting.gates import GateOutcome, GateResult
from convsim_core.flyting.npc import (
    OPPONENT_FALLBACK_COUNTER,
    OPPONENT_FALLBACK_REACTION,
    clean_opponent_line,
    compose_counter_volley_prompt,
    compose_reaction_prompt,
)
from convsim_core.flyting.scoring import VolleyScore
from convsim_core.flyting.service import PreparedVolley, VolleyScoringService
from convsim_core.flyting.session import (
    ExchangeResult,
    FlytingRunState,
    RunOutcome,
    record_npc_volley,
    record_player_volley,
    resolve_batting_practice,
    resolve_exchange,
    shot_clock_expired,
)
from convsim_core.flyting.volley import VolleyInputError
from convsim_core.runtime.base import ChatRuntime
from convsim_core.runtime.types import ChatFinal, ChatMessage, ChatRequest, ChatToken
from convsim_core.scenario_state import ScenarioVariableDef
from convsim_core.storage.repositories import flyting_repo

logger = logging.getLogger(__name__)

# The judge verdict is a small object; 512 tokens is ample and keeps a drifting
# model from monologuing into the latency budget.
JUDGE_MAX_TOKENS = 512
# Temperature 0 plus the grammar constraint is what makes two runs of the same
# volley on the same model produce the same verdict.
JUDGE_TEMPERATURE = 0.0

OPPONENT_MAX_TOKENS = 160

# How many earlier lines are quoted to the judge for callback verification.
_CALLBACK_WINDOW = 4


class FlytingRunOver(RuntimeError):
    """Raised when a volley is submitted to a run that has already finished."""


@dataclass
class VolleyTurnResult:
    """Everything one submitted volley produced."""

    player_score: VolleyScore
    state: FlytingRunState
    npc_line: Optional[str] = None
    npc_score: Optional[VolleyScore] = None
    exchange: Optional[ExchangeResult] = None
    run_outcome: Optional[str] = None
    player_event_id: Optional[int] = None
    npc_event_id: Optional[int] = None
    turn_number: int = 0
    judge_events: Optional[List[JudgeEvent]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "player_volley": self.player_score.to_dict(),
            "npc_line": self.npc_line,
            "npc_volley": self.npc_score.to_dict() if self.npc_score else None,
            "run": self.state.to_dict(),
            "exchange": (
                {
                    "momentum": self.exchange.momentum,
                    "momentum_delta": self.exchange.momentum_delta,
                    "clamped": self.exchange.clamped,
                }
                if self.exchange
                else None
            ),
            "run_outcome": self.run_outcome,
            "turn_number": self.turn_number,
        }


async def _collect_output(
    runtime: ChatRuntime, request: ChatRequest
) -> tuple[str, Optional[Dict[str, Any]]]:
    """Stream a runtime response to completion and return (text, structured)."""
    raw_text = ""
    structured: Optional[Dict[str, Any]] = None
    async for chunk in runtime.chat_stream(request):
        if isinstance(chunk, ChatFinal):
            raw_text = chunk.text
            structured = chunk.structured
            break  # ChatFinal is authoritative; trailing tokens must not append.
        if isinstance(chunk, ChatToken):
            raw_text += chunk.text
    return raw_text, structured


async def judge_volley(
    prepared: PreparedVolley,
    service: VolleyScoringService,
    runtime: Optional[ChatRuntime],
    *,
    speaker: str = "player",
    opponent_last_line: Optional[str] = None,
    earlier_exchanges: Sequence[str] = (),
    theme_uses: Optional[Dict[str, int]] = None,
    discovered_traits: Optional[Sequence[str]] = None,
    events: Optional[List[JudgeEvent]] = None,
) -> Optional[VolleyJudgment]:
    """Make one judge call (plus at most one retry) and verify the verdict.

    Returns None when no judge is available or its output is unusable twice —
    the caller then scores the volley from its mechanics and flags it, rather
    than inventing numbers no model produced.
    """
    if runtime is None or not prepared.needs_judge:
        return None

    judge_input = service.judge_input(
        prepared,
        speaker=speaker,
        opponent_last_line=opponent_last_line,
        earlier_exchanges=earlier_exchanges,
        theme_uses=theme_uses,
    )
    prompt = compose_volley_judge_prompt(judge_input)

    def _request(user_prompt: str) -> ChatRequest:
        return ChatRequest(
            messages=[
                ChatMessage(role="system", content=prompt.system_prompt),
                ChatMessage(role="user", content=user_prompt),
            ],
            json_schema=FLYTING_JUDGE_OUTPUT_SCHEMA,
            temperature=JUDGE_TEMPERATURE,
            max_tokens=JUDGE_MAX_TOKENS,
        )

    def _parse(raw: str) -> Optional[VolleyJudgment]:
        return parse_volley_judgment(
            raw,
            volley_text=prepared.volley.text,
            attack_surface=service.context.attack_surface,
            riposte_allowed=bool(opponent_last_line),
            callback_allowed=bool(earlier_exchanges),
            discovered_traits=set(discovered_traits or ()),
            events=events,
        )

    for attempt, user_prompt in enumerate((prompt.user_prompt, JUDGE_REPAIR_PROMPT)):
        try:
            raw, structured = await _collect_output(runtime, _request(user_prompt))
        except Exception as exc:  # noqa: BLE001 — a judge outage must not end a run
            logger.warning("Judge call failed (attempt %d): %s", attempt + 1, exc)
            if events is not None:
                events.append(JudgeEvent("judge_call_failure", reason=str(exc)))
            return None
        # A runtime with native JSON-schema support hands back a parsed object;
        # re-serialising it means the extraction step always succeeds.
        payload = json.dumps(structured) if structured is not None else raw
        judgment = _parse(payload)
        if judgment is not None:
            if attempt == 1 and events is not None:
                events.append(JudgeEvent("judge_repair_success"))
            return judgment
        logger.warning("Judge output unusable on attempt %d", attempt + 1)

    return None


async def _opponent_line(
    runtime: Optional[ChatRuntime],
    *,
    system: str,
    user: str,
    fallback: str,
    max_words: int,
    temperature: float,
) -> str:
    if runtime is None:
        return fallback
    request = ChatRequest(
        messages=[
            ChatMessage(role="system", content=system),
            ChatMessage(role="user", content=user),
        ],
        temperature=temperature,
        max_tokens=OPPONENT_MAX_TOKENS,
    )
    try:
        raw, _ = await _collect_output(runtime, request)
    except Exception as exc:  # noqa: BLE001 — the exchange continues regardless
        logger.warning("Opponent generation failed: %s", exc)
        return fallback
    return clean_opponent_line(raw, fallback=fallback, max_words=max_words)


async def process_volley(
    session_row: sqlite3.Row,
    player_text: str,
    *,
    service: VolleyScoringService,
    npc: NpcData,
    runtime: Optional[ChatRuntime],
    conn: sqlite3.Connection,
    player_role_label: str = "your opponent",
    player_role_brief: str = "",
    elapsed_since_prompt_s: Optional[float] = None,
    elapsed_total_s: Optional[float] = None,
    save_transcript: bool = True,
    momentum_variable_def: Optional[ScenarioVariableDef] = None,
) -> VolleyTurnResult:
    """Score one player volley, answer it, update the run, and persist everything.

    Raises ``FlytingRunOver`` if the run has already finished and
    ``VolleyInputError`` if the text cannot be a volley at all.
    """
    session_id: str = session_row["session_id"]
    state = FlytingRunState.from_dict(_load_run_state(session_row))
    if state.is_over:
        raise FlytingRunOver(
            f"This run already ended ({state.outcome}). Start another to keep volleying."
        )

    config = service.context.flyting
    is_bout = state.play_format is PlayFormat.BOUT
    received_at = datetime.now(timezone.utc).isoformat()

    prior_texts = flyting_repo.volley_texts(conn, session_id)
    prepared = service.prepare(
        player_text,
        prior_volleys=prior_texts,
        prior_below_the_belt=state.foul_counts.get("below_the_belt", 0),
    )

    # The shot clock is a reflex constraint, so a late volley is a whiff whatever
    # it says — and there is no point paying for a judge call on it.
    #
    # It is a batting-practice mechanic only (see docs/flyting.md): a bout is a
    # contest of lines, not of reflexes, and zeroing a late volley there would
    # cost the player the exchange, hand the round to the opponent, and swing
    # momentum for the crime of thinking. The engine is the authority on that,
    # whatever elapsed time a client chooses to report.
    extra_flags: List[str] = []
    if (
        not is_bout
        and elapsed_since_prompt_s is not None
        and shot_clock_expired(state, elapsed_since_prompt_s)
    ):
        extra_flags.append("shot_clock_expired")
        prepared.gate = GateResult(
            outcome=GateOutcome.DUD,
            reason="shot_clock_expired",
            flags=["shot_clock_expired"],
            umpire_mock="Too slow. The crowd has moved on.",
        )

    judge_events: List[JudgeEvent] = []
    npc_last_line = _last_npc_line(conn, session_id) if is_bout else None
    earlier = prior_texts[-_CALLBACK_WINDOW:-1] if len(prior_texts) > 1 else []

    judgment = await judge_volley(
        prepared,
        service,
        runtime,
        speaker="player",
        opponent_last_line=npc_last_line,
        earlier_exchanges=earlier,
        theme_uses=state.theme_uses,
        discovered_traits=state.discovered_traits,
        events=judge_events,
    )

    player_score = service.compose(
        prepared,
        judgment,
        volley_number=state.player_volleys + 1,
        speaker="player",
        theme_uses=state.theme_uses,
        recent_devices=state.recent_devices,
        # Heat pays in batting practice only; a bout is scored on raw totals.
        heat=1.0 if is_bout else state.heat,
        riposte_bonus=config.bout.riposte_bonus if is_bout else 0,
        extra_flags=extra_flags,
    )

    # ── The opponent answers ────────────────────────────────────────────────
    npc_line: Optional[str] = None
    npc_score: Optional[VolleyScore] = None
    exchange: Optional[ExchangeResult] = None

    if is_bout:
        tier = config.bout.tier_profile
        system, user = compose_counter_volley_prompt(
            npc=npc,
            config=config,
            tier=tier,
            scenario_title=service.context.scenario_title,
            setting_brief=service.context.setting_brief,
            player_role_label=player_role_label,
            player_role_brief=player_role_brief,
            player_last_line=prepared.volley.text,
            recent_lines=prior_texts[-_CALLBACK_WINDOW:],
            content_rating=service.context.content_rating,
        )
        npc_line = await _opponent_line(
            runtime, system=system, user=user, fallback=OPPONENT_FALLBACK_COUNTER,
            max_words=tier.max_words, temperature=tier.temperature,
        )
        # The opponent's volley is scored by the same pipeline, and a fallback
        # line is not a volley the player has to beat: it is scored as the empty
        # gesture it is, which is exactly what the pipeline will conclude.
        npc_prepared = service.prepare(
            npc_line,
            # The player's line joins the corpus only if it was worth something,
            # the same rule ``volley_texts`` applies to the rest of the session.
            prior_volleys=(
                prior_texts + [prepared.volley.text]
                if player_score.score > 0
                else prior_texts
            ),
        )
        npc_judgment = await judge_volley(
            npc_prepared,
            service,
            runtime,
            speaker="npc",
            opponent_last_line=prepared.volley.text,
            theme_uses=state.theme_uses,
            events=judge_events,
        )
        npc_score = service.compose(
            npc_prepared,
            npc_judgment,
            volley_number=state.npc_volleys + 1,
            speaker="npc",
            theme_uses=state.theme_uses,
            heat=1.0,
            riposte_bonus=config.bout.riposte_bonus,
        )
    else:
        system, user = compose_reaction_prompt(
            npc=npc,
            config=config,
            scenario_title=service.context.scenario_title,
            player_last_line=prepared.volley.text,
            content_rating=service.context.content_rating,
        )
        npc_line = await _opponent_line(
            runtime, system=system, user=user, fallback=OPPONENT_FALLBACK_REACTION,
            max_words=20, temperature=0.8,
        )

    # ── Fold into the run ───────────────────────────────────────────────────
    record_player_volley(state, player_score)
    if npc_score is not None:
        record_npc_volley(state, npc_score)

    if elapsed_total_s is not None:
        state.elapsed_s = elapsed_total_s

    if is_bout:
        exchange = resolve_exchange(
            state,
            player_score.score,
            npc_score.score if npc_score else 0,
            config.bout,
            variable_def=momentum_variable_def,
        )
        player_score.momentum = exchange.momentum
        if npc_score is not None:
            npc_score.momentum = exchange.momentum
    else:
        resolve_batting_practice(state, foul_ended=player_score.gate.ends_session)

    if player_score.gate.ends_session:
        state.outcome = RunOutcome.FOULED_OUT.value

    run_outcome = state.outcome if state.is_over else None
    turn_number = int(session_row["turn_count"]) + 1

    player_event_id, npc_event_id = _persist(
        conn,
        session_id=session_id,
        state=state,
        turn_number=turn_number,
        player_score=player_score,
        npc_line=npc_line,
        npc_score=npc_score,
        received_at=received_at,
        run_outcome=run_outcome,
        save_transcript=save_transcript,
    )

    return VolleyTurnResult(
        player_score=player_score,
        state=state,
        npc_line=npc_line,
        npc_score=npc_score,
        exchange=exchange,
        run_outcome=run_outcome,
        player_event_id=player_event_id,
        npc_event_id=npc_event_id,
        turn_number=turn_number,
        judge_events=judge_events,
    )


# ---------------------------------------------------------------------------
# Session row helpers
# ---------------------------------------------------------------------------


def _load_run_state(session_row: sqlite3.Row) -> Optional[Dict[str, Any]]:
    try:
        raw = session_row["flyting_state_json"]
    except (IndexError, KeyError):
        return None
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _last_npc_line(conn: sqlite3.Connection, session_id: str) -> Optional[str]:
    row = conn.execute(
        "SELECT content FROM turn_session_turns WHERE session_id = ? AND role = 'npc' "
        "ORDER BY turn_number DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    return row["content"] if row is not None else None


def _persist(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    state: FlytingRunState,
    turn_number: int,
    player_score: VolleyScore,
    npc_line: Optional[str],
    npc_score: Optional[VolleyScore],
    received_at: str,
    run_outcome: Optional[str],
    save_transcript: bool,
) -> tuple[Optional[int], Optional[int]]:
    """Write both turns, both scorecards, the events, and the run state atomically."""
    now = datetime.now(timezone.utc).isoformat()
    player_turn_number = turn_number * 2 - 1
    npc_turn_number = turn_number * 2
    flow_state = "Ended" if run_outcome else "PlayerTurnListening"

    # Momentum is mirrored into the ordinary state-variable snapshot so the
    # existing meter UI and branch-session fork points see it like any other
    # meter. Heat is deliberately not: it is a 1.0-2.0 multiplier, and the state
    # engine stores integers, so it lives on the run state and the scorecard
    # where it can be shown honestly.
    state_vars = {"momentum": state.momentum}
    snapshot = json.dumps({"state_vars": state_vars, "fired_events": []})

    with conn:
        player_cursor = conn.execute(
            "INSERT INTO turn_session_turns "
            "(session_id, turn_number, role, content, source_mode, flow_state_after, created_at) "
            "VALUES (?, ?, 'player', ?, 'text-only', ?, ?)",
            (session_id, player_turn_number, player_score.text, flow_state, received_at),
        )
        npc_cursor = None
        if npc_line:
            npc_cursor = conn.execute(
                "INSERT INTO turn_session_turns "
                "(session_id, turn_number, role, content, emotion, state_delta_json, "
                "event_flags_json, safety_json, flow_state_after, state_snapshot_json, created_at) "
                "VALUES (?, ?, 'npc', ?, 'neutral', ?, '[]', ?, ?, ?, ?)",
                (
                    session_id,
                    npc_turn_number,
                    npc_line,
                    json.dumps({"momentum": state.momentum}),
                    json.dumps({"status": "ok", "reason": None}),
                    flow_state,
                    snapshot,
                    now,
                ),
            )

        flyting_repo.insert_volley(
            conn, session_id, player_score.to_dict(), text=player_score.text
        )
        if npc_score is not None:
            flyting_repo.insert_volley(
                conn, session_id, npc_score.to_dict(), text=npc_score.text
            )

        events: List[tuple] = [(
            session_id, turn_number, "flyting_volley",
            json.dumps({
                "speaker": "player",
                "score": player_score.score,
                "band": player_score.band,
                "heat": player_score.heat,
                "banked_score": player_score.banked_score,
                "flags": player_score.flags,
                "umpire_line": (
                    player_score.judgment.umpire_line if player_score.judgment
                    else player_score.gate.umpire_mock
                ),
            }), now,
        )]
        if npc_score is not None:
            events.append((
                session_id, turn_number, "flyting_volley",
                json.dumps({
                    "speaker": "npc",
                    "score": npc_score.score,
                    "band": npc_score.band,
                    "flags": npc_score.flags,
                }), now,
            ))
            events.append((
                session_id, turn_number, "flyting_exchange",
                json.dumps({
                    "momentum": state.momentum,
                    "player_total": state.player_total,
                    "npc_total": state.npc_total,
                    "round_number": state.round_number,
                }), now,
            ))
        if player_score.gate.foul is not None:
            events.append((
                session_id, turn_number, "flyting_foul",
                json.dumps({
                    "foul": player_score.gate.foul.value,
                    "reason": player_score.gate.reason,
                    "ends_session": player_score.gate.ends_session,
                }), now,
            ))
        if player_score.audience_reaction:
            events.append((
                session_id, turn_number, "audience_reaction",
                json.dumps({"line": player_score.audience_reaction, "score": player_score.score}), now,
            ))
        if run_outcome:
            events.append((
                session_id, turn_number, "session_ending",
                json.dumps({"ending_type": run_outcome, "summary": None}), now,
            ))
        conn.executemany(
            "INSERT INTO turn_session_events "
            "(session_id, turn_number, event_type, payload_json, occurred_at) "
            "VALUES (?, ?, ?, ?, ?)",
            events,
        )

        if save_transcript:
            rows = [(session_id, player_turn_number, "player", player_score.text)]
            if npc_line:
                rows.append((session_id, npc_turn_number, "npc", npc_line))
            conn.executemany(
                "INSERT INTO session_transcript_fts(session_id, turn_number, role, content) "
                "VALUES (?, ?, ?, ?)",
                rows,
            )

        conn.execute(
            "UPDATE turn_sessions SET state_vars_json = ?, flyting_state_json = ?, "
            "turn_count = ?, flow_state = ?, ending_type = ? WHERE session_id = ?",
            (
                json.dumps(state_vars),
                json.dumps(state.to_dict()),
                turn_number,
                flow_state,
                run_outcome,
                session_id,
            ),
        )

    return (
        player_cursor.lastrowid,
        npc_cursor.lastrowid if npc_cursor is not None else None,
    )
