# SPDX-License-Identifier: Apache-2.0
"""Live session events over WebSocket (issue #538).

The REST turn response stays the commit and the source of truth. The socket is
how the player sees the turn *while* it happens: the stage it is in, the NPC's
words as each checked sentence is released, and the state change at commit.
With no socket connected nothing here runs and the turn behaves exactly as it
did before. Events are never persisted; a client that missed them reads the
committed turn from the REST response or the transcript.

Every message is the envelope ``packages/shared/src/types/ws-events.ts``
describes: ``{seq, session_id, type, ts, payload}``, with ``seq`` a
per-session counter that advances for every event whether or not a socket is
listening, so a reconnecting client can tell it missed something.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

from fastapi import WebSocket

from convsim_core.services.turn_timing import TurnClock

logger = logging.getLogger(__name__)

#: How long one socket may stall a send before it is dropped. The engine's
#: stream must never wait on a slow or dead browser tab.
_SEND_TIMEOUT_S = 1.0


class SessionEventBus:
    """Per-session WebSocket fan-out with a monotonically increasing ``seq``."""

    def __init__(self) -> None:
        self._sockets: Dict[str, Set[WebSocket]] = {}
        self._seq: Dict[str, int] = {}

    # ── registration ────────────────────────────────────────────────────

    def register(self, session_id: str, websocket: WebSocket) -> None:
        self._sockets.setdefault(session_id, set()).add(websocket)

    def unregister(self, session_id: str, websocket: WebSocket) -> None:
        sockets = self._sockets.get(session_id)
        if sockets is None:
            return
        sockets.discard(websocket)
        if not sockets:
            # Keep the seq counter: it must survive reconnects so a client can
            # detect a gap. Only the socket set is dropped.
            del self._sockets[session_id]

    def has_listeners(self, session_id: str) -> bool:
        return bool(self._sockets.get(session_id))

    def listener_count(self, session_id: str) -> int:
        return len(self._sockets.get(session_id, ()))

    def next_seq(self, session_id: str) -> int:
        self._seq[session_id] = self._seq.get(session_id, 0) + 1
        return self._seq[session_id]

    # ── sending ─────────────────────────────────────────────────────────

    def envelope(self, session_id: str, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "seq": self.next_seq(session_id),
            "session_id": session_id,
            "type": event_type,
            "ts": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }

    async def send_to(self, websocket: WebSocket, message: Dict[str, Any]) -> bool:
        try:
            await asyncio.wait_for(websocket.send_json(message), timeout=_SEND_TIMEOUT_S)
            return True
        except Exception as exc:  # noqa: BLE001 — a dead socket must never fail the turn
            logger.debug("session socket send failed: %s", exc)
            return False

    async def broadcast(self, session_id: str, event_type: str, payload: Dict[str, Any]) -> int:
        """Send one event to every socket on the session; returns its ``seq``.

        The counter advances even with no listener, so a client that connects
        later sees a gap rather than a counter that restarts at 1.
        """
        message = self.envelope(session_id, event_type, payload)
        sockets = list(self._sockets.get(session_id, ()))
        for ws in sockets:
            if not await self.send_to(ws, message):
                self.unregister(session_id, ws)
        return int(message["seq"])

    async def close_session(self, session_id: str, reason: str = "Session ended") -> None:
        for ws in list(self._sockets.get(session_id, ())):
            try:
                await ws.close(code=1000, reason=reason)
            except Exception:  # noqa: BLE001
                pass
            self.unregister(session_id, ws)


class SessionTurnStreamer:
    """The turn pipeline's view of the bus for one turn (see ``TurnStreamer``).

    Carries the turn's clock so every ``turn.progress`` event reports how long
    the turn has been running, measured from the moment the request arrived.
    """

    def __init__(self, bus: SessionEventBus, session_id: str, clock: TurnClock) -> None:
        self._bus = bus
        self._session_id = session_id
        self._clock = clock
        self.output_tokens = 0

    async def progress(
        self,
        stage: str,
        prompt: Optional[Dict[str, Optional[int]]] = None,
    ) -> None:
        await self._bus.broadcast(self._session_id, "turn.progress", {
            "stage": stage,
            "prompt": prompt,
            "output_tokens": self.output_tokens,
            "elapsed_ms": self._clock.elapsed_ms(),
        })

    async def token(self, text: str) -> None:
        await self._bus.broadcast(self._session_id, "npc.token", {"text": text})

    async def final(self, content: str) -> None:
        await self._bus.broadcast(self._session_id, "npc.final", {"content": content})
