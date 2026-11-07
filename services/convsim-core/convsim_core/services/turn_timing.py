# SPDX-License-Identifier: Apache-2.0
"""What each NPC turn actually cost (issue #519).

One record per NPC turn, built from a monotonic clock in the core and from
whatever the engine itself reported. Everything else in the turn-speed work
(#518) — the wait estimate, the speed check, the per-reply details — reads this
record rather than guessing. A field the engine or the pipeline cannot supply is
``None``; nothing here is estimated silently.

The record is persisted as a ``turn_timing`` event in ``turn_session_events``
and mirrored in TypeScript as ``TurnTiming`` in ``packages/shared``. Keep the
two in step.

The six stages of a turn are defined here and cited everywhere else::

    waiting    the engine has the request but is not reading yet (loading, or
               queued behind other work)
    reading    prompt evaluation
    writing    the model is producing tokens
    finishing  the bookkeeping after the spoken line, up to the commit
    checking   a repair or safety retry is running
    voice      speech synthesis of the reply
"""
from __future__ import annotations

import json
import sqlite3
import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from pydantic import BaseModel

from convsim_core.runtime.types import ChatFinal, ChatProgress, ChatTimings, FinishReason

#: The stages of an NPC turn, in the order a turn passes through them.
TURN_STAGES: tuple[str, ...] = ("waiting", "reading", "writing", "finishing", "checking", "voice")
TurnStage = Literal["waiting", "reading", "writing", "finishing", "checking", "voice"]

#: ``event_type`` of the persisted record in ``turn_session_events``.
TURN_TIMING_EVENT_TYPE = "turn_timing"

#: How many recent records the rolling medians are taken over.
ROLLING_WINDOW = 20

ExtraCallKind = Literal["repair", "safety_retry"]


class ExtraCall(BaseModel):
    kind: ExtraCallKind
    ms: float
    tokens: int | None = None


class VoiceTiming(BaseModel):
    synth_ms: float | None = None
    first_audio_ms: float | None = None


class TurnTokens(BaseModel):
    prompt: int | None = None
    cached: int | None = None
    evaluated: int | None = None
    output: int | None = None
    spoken: int | None = None


class TurnRates(BaseModel):
    reading_tps: float | None = None
    writing_tps: float | None = None


class TurnContext(BaseModel):
    #: The model as the engine named it in its reply.
    model_id: str
    #: The registry id of the active model at the time, when the app knew one.
    registry_model_id: str | None = None
    runtime_id: str
    engine_variant: str | None = None
    n_ctx: int | None = None
    n_batch: int | None = None
    threads: int | None = None
    #: True when fewer than half the prompt tokens came from the engine's cache;
    #: None when the engine did not report cache use.
    cold: bool | None = None


class TurnTiming(BaseModel):
    """One NPC turn's cost. Milliseconds are measured, never estimated."""

    total_ms: float
    waiting_ms: float | None = None
    reading_ms: float | None = None
    #: request received → first generated token
    first_token_ms: float | None = None
    #: request received → first reply text released to the player (#538)
    first_words_ms: float | None = None
    #: request received → spoken line complete (#538)
    reply_done_ms: float | None = None
    writing_ms: float | None = None
    #: compose + parse + persist
    other_ms: float = 0.0
    extra_calls: list[ExtraCall] = []
    salvaged: bool = False
    fallback: bool = False
    stopped: bool = False
    finish_reason: FinishReason | None = None
    voice: VoiceTiming | None = None
    tokens: TurnTokens = TurnTokens()
    rates: TurnRates = TurnRates()
    context: TurnContext


def _ms(seconds: float) -> float:
    return round(seconds * 1000.0, 1)


@dataclass
class TurnClock:
    """A monotonic clock started when the player's turn arrived at the core."""

    started: float = field(default_factory=time.perf_counter)

    def elapsed_ms(self) -> float:
        return _ms(time.perf_counter() - self.started)

    def now(self) -> float:
        return time.perf_counter()


@dataclass
class StreamObservation:
    """Timestamps and signals collected while one runtime stream was consumed."""

    sent_at: float
    first_progress_at: float | None = None
    first_token_at: float | None = None
    final_at: float | None = None
    last_progress: ChatProgress | None = None
    final: ChatFinal | None = None

    def saw_progress(self, chunk: ChatProgress, at: float) -> None:
        if self.first_progress_at is None:
            self.first_progress_at = at
        self.last_progress = chunk

    def saw_token(self, at: float) -> None:
        if self.first_token_at is None:
            self.first_token_at = at

    def saw_final(self, final: ChatFinal, at: float) -> None:
        self.final = final
        self.final_at = at


@dataclass
class TurnTimingBuilder:
    """Accumulates one turn's measurements as the pipeline runs.

    The pipeline fills in the stages it can see; the router adds voice and the
    total after synthesis, then persists the record (see ``routers/sessions.py``).
    """

    clock: TurnClock
    runtime_id: str
    registry_model_id: str | None = None
    compose_ms: float = 0.0
    parse_ms: float = 0.0
    persist_ms: float = 0.0
    observation: StreamObservation | None = None
    extra_calls: list[ExtraCall] = field(default_factory=list)
    fallback: bool = False
    salvaged: bool = False
    stopped: bool = False
    first_words_ms: float | None = None
    reply_done_ms: float | None = None
    voice: VoiceTiming | None = None
    n_ctx: int | None = None
    n_batch: int | None = None
    threads: int | None = None
    engine_variant: str | None = None

    def record_extra_call(self, kind: ExtraCallKind, ms: float, tokens: int | None) -> None:
        self.extra_calls.append(ExtraCall(kind=kind, ms=round(ms, 1), tokens=tokens))

    def build(self) -> TurnTiming:
        obs = self.observation
        final = obs.final if obs else None
        timings: ChatTimings | None = final.timings if final else None

        first_token_ms: float | None = None
        writing_ms: float | None = None
        reading_ms: float | None = None
        waiting_ms: float | None = None
        if obs is not None:
            if obs.first_token_at is not None:
                first_token_ms = _ms(obs.first_token_at - self.clock.started)
                if obs.final_at is not None:
                    writing_ms = _ms(obs.final_at - obs.first_token_at)
            if timings is not None and timings.prompt_ms is not None:
                reading_ms = round(timings.prompt_ms, 1)
                if obs.first_token_at is not None:
                    # Everything between sending the request and the first
                    # token that the engine did not spend reading: loading, or
                    # queued behind other work. Both numbers are measured.
                    waiting_ms = max(0.0, _ms(obs.first_token_at - obs.sent_at) - reading_ms)
            elif obs.first_progress_at is not None:
                waiting_ms = _ms(obs.first_progress_at - obs.sent_at)
                if obs.first_token_at is not None:
                    reading_ms = _ms(obs.first_token_at - obs.first_progress_at)
            if timings is not None and timings.generation_ms is not None:
                writing_ms = round(timings.generation_ms, 1)

        tokens = TurnTokens()
        rates = TurnRates()
        if timings is not None:
            tokens = TurnTokens(
                prompt=timings.prompt_tokens,
                cached=timings.cached_tokens,
                evaluated=timings.evaluated_tokens,
                output=timings.output_tokens,
            )
            rates = TurnRates(reading_tps=timings.reading_tps, writing_tps=timings.writing_tps)
        if final is not None:
            # The adapters' older counts, kept when the engine gave no timings
            # block but did report usage. Zero means "not reported".
            if tokens.prompt is None and final.input_tokens > 0:
                tokens.prompt = final.input_tokens
            if tokens.output is None and final.output_tokens > 0:
                tokens.output = final.output_tokens

        cold: bool | None = None
        if tokens.prompt is not None and tokens.cached is not None and tokens.prompt > 0:
            cold = tokens.cached < tokens.prompt / 2

        return TurnTiming(
            total_ms=self.clock.elapsed_ms(),
            waiting_ms=waiting_ms,
            reading_ms=reading_ms,
            first_token_ms=first_token_ms,
            first_words_ms=self.first_words_ms,
            reply_done_ms=self.reply_done_ms,
            writing_ms=writing_ms,
            other_ms=round(self.compose_ms + self.parse_ms + self.persist_ms, 1),
            extra_calls=list(self.extra_calls),
            salvaged=self.salvaged,
            fallback=self.fallback,
            stopped=self.stopped,
            finish_reason=final.finish_reason if final else None,
            voice=self.voice,
            tokens=tokens,
            rates=rates,
            context=TurnContext(
                model_id=final.model_id if final else "",
                registry_model_id=self.registry_model_id,
                runtime_id=self.runtime_id,
                engine_variant=self.engine_variant,
                n_ctx=self.n_ctx,
                n_batch=self.n_batch,
                threads=self.threads,
                cold=cold,
            ),
        )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def persist_turn_timing(
    conn: sqlite3.Connection,
    session_id: str,
    turn_number: int,
    timing: TurnTiming,
    occurred_at: str,
) -> int:
    """Write the record as a ``turn_timing`` event; returns the event row id.

    Lives in ``turn_session_events`` so it is deleted with the session (the
    table cascades on ``turn_sessions``) and by "Clear all local data", and so
    the session export already carries it. No migration.
    """
    with conn:
        cursor = conn.execute(
            "INSERT INTO turn_session_events "
            "(session_id, turn_number, event_type, payload_json, occurred_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, turn_number, TURN_TIMING_EVENT_TYPE, timing.model_dump_json(), occurred_at),
        )
    return int(cursor.lastrowid)


def load_turn_timings(conn: sqlite3.Connection, session_id: str) -> dict[int, dict[str, Any]]:
    """The persisted records of one session, keyed by game turn number."""
    rows = conn.execute(
        "SELECT turn_number, payload_json FROM turn_session_events "
        "WHERE session_id = ? AND event_type = ? ORDER BY id ASC",
        (session_id, TURN_TIMING_EVENT_TYPE),
    ).fetchall()
    out: dict[int, dict[str, Any]] = {}
    for row in rows:
        if row["turn_number"] is None:
            continue
        try:
            out[int(row["turn_number"])] = json.loads(row["payload_json"])
        except (ValueError, TypeError):
            continue
    return out


# ---------------------------------------------------------------------------
# Rolling speeds
# ---------------------------------------------------------------------------


class RollingSpeeds(BaseModel):
    """This machine's recent medians for one model and engine configuration.

    Every figure is None until at least one recorded turn supplied it.
    """

    runtime_id: str | None
    model_id: str | None
    samples: int
    reading_tps: float | None = None
    writing_tps: float | None = None
    first_token_ms: float | None = None
    first_words_ms: float | None = None
    total_ms: float | None = None


def _median(values: list[float]) -> float | None:
    clean = [float(v) for v in values if isinstance(v, (int, float))]
    if not clean:
        return None
    return round(statistics.median(clean), 1)


def _matches_config(ctx: dict[str, Any], runtime_id: str | None, model_id: str | None) -> bool:
    if runtime_id is not None and ctx.get("runtime_id") != runtime_id:
        return False
    if model_id is not None:
        # The registry id when the record has one, else the engine's own name.
        recorded = ctx.get("registry_model_id") or ctx.get("model_id")
        if recorded != model_id:
            return False
    return True


def rolling_speeds(
    conn: sqlite3.Connection,
    *,
    runtime_id: str | None,
    model_id: str | None,
    window: int = ROLLING_WINDOW,
) -> RollingSpeeds:
    """Medians over the most recent recorded turns for ``runtime_id``/``model_id``.

    A None filter matches every record. Turns marked ``stopped`` or ``fallback``
    are left out: a cancelled or canned reply says nothing about the pace.
    """
    rows = conn.execute(
        "SELECT payload_json FROM turn_session_events "
        "WHERE event_type = ? ORDER BY id DESC LIMIT ?",
        (TURN_TIMING_EVENT_TYPE, max(window * 10, window)),
    ).fetchall()
    records: list[dict[str, Any]] = []
    for row in rows:
        try:
            rec = json.loads(row["payload_json"])
        except (ValueError, TypeError):
            continue
        ctx = rec.get("context") or {}
        if not _matches_config(ctx, runtime_id, model_id):
            continue
        if rec.get("stopped") or rec.get("fallback"):
            continue
        records.append(rec)
        if len(records) >= window:
            break

    def pick(path: tuple[str, ...]) -> list[float]:
        out: list[float] = []
        for rec in records:
            node: Any = rec
            for key in path:
                node = node.get(key) if isinstance(node, dict) else None
            if isinstance(node, (int, float)):
                out.append(float(node))
        return out

    return RollingSpeeds(
        runtime_id=runtime_id,
        model_id=model_id,
        samples=len(records),
        reading_tps=_median(pick(("rates", "reading_tps"))),
        writing_tps=_median(pick(("rates", "writing_tps"))),
        first_token_ms=_median(pick(("first_token_ms",))),
        first_words_ms=_median(pick(("first_words_ms",))),
        total_ms=_median(pick(("total_ms",))),
    )
