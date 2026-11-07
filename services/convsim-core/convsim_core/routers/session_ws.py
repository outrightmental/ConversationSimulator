# SPDX-License-Identifier: Apache-2.0
"""``/ws/session/{session_id}`` — live events for one session (issue #538).

Served by the core itself. The web client has dialled this address since the
interim ``apps/api`` backend served it; the core answered every upgrade with
403 until now (the log in #489).

The route checks ``Origin`` itself: CORS middleware does not cover WebSocket
upgrades, and the local-first promise means only the packaged webview's
origins and the dev server's may connect from a browser. A request with no
``Origin`` header is not a browser page and is accepted. The check runs before
the handshake is accepted, so a rejected origin gets an HTTP 403, not a socket.

On connect the server sends the current ``session.state`` so a reconnecting
client can resync. Client-to-server messages are read and ignored until #540
adds the cancel message.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from convsim_core.origins import websocket_origin_allowed
from convsim_core.scenario_state import build_variable_defs, partition_state_by_visibility
from convsim_core.services.session_events import SessionEventBus

logger = logging.getLogger(__name__)

router = APIRouter()

#: WebSocket close code for a policy violation (RFC 6455 §7.4.1).
_POLICY_VIOLATION = 1008


def _bus(websocket: WebSocket) -> SessionEventBus:
    bus = getattr(websocket.app.state, "session_bus", None)
    if bus is None:
        bus = SessionEventBus()
        websocket.app.state.session_bus = bus
    return bus


@router.websocket("/ws/session/{session_id}")
async def session_socket(websocket: WebSocket, session_id: str) -> None:
    if not websocket_origin_allowed(websocket.headers.get("origin")):
        logger.info("session socket refused: origin %r is not a local UI", websocket.headers.get("origin"))
        # Closing before accept() answers the handshake with HTTP 403.
        await websocket.close(code=_POLICY_VIOLATION)
        return

    conn = websocket.app.state.db.connection()
    row = conn.execute(
        "SELECT flow_state, state_vars_json, ending_type FROM turn_sessions WHERE session_id = ?",
        (session_id,),
    ).fetchone()

    await websocket.accept()
    bus = _bus(websocket)

    if row is None:
        await bus.send_to(websocket, bus.envelope(session_id, "error", {
            "code": "SESSION_NOT_FOUND",
            "message": f"Session {session_id!r} not found",
        }))
        await websocket.close(code=_POLICY_VIOLATION, reason="Session not found")
        return

    bus.register(session_id, websocket)
    try:
        state_vars = json.loads(row["state_vars_json"] or "{}")
        visible, _ = partition_state_by_visibility(state_vars, build_variable_defs())
        await bus.send_to(websocket, bus.envelope(session_id, "session.state", {
            "state": row["flow_state"],
            "state_vars": visible,
            "ending_type": row["ending_type"],
        }))
        while True:
            # Nothing is acted on yet (#540 adds cancel); reading keeps the
            # connection's close frames flowing so a dropped tab is noticed.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001 — a socket failure must never surface as a 500
        logger.debug("session socket %s closed with %s", session_id, exc)
    finally:
        bus.unregister(session_id, websocket)
