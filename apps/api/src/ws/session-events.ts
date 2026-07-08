// SPDX-License-Identifier: Apache-2.0
import type { WebSocket } from '@fastify/websocket';
import type { WsEvent } from '@convsim/shared';

interface SessionWsState {
  connections: Set<WebSocket>;
  seq: number;
}

const sessions = new Map<string, SessionWsState>();

function getOrCreate(sessionId: string): SessionWsState {
  let state = sessions.get(sessionId);
  if (!state) {
    state = { connections: new Set(), seq: 0 };
    sessions.set(sessionId, state);
  }
  return state;
}

export function registerConnection(sessionId: string, ws: WebSocket): void {
  getOrCreate(sessionId).connections.add(ws);
}

export function removeConnection(sessionId: string, ws: WebSocket): void {
  const state = sessions.get(sessionId);
  if (!state) return;
  state.connections.delete(ws);
  // Do NOT delete the Map entry when the last client leaves. The seq counter
  // must survive reconnects so clients can detect missed events by comparing
  // against the seq they last saw. The entry is removed only in
  // closeSessionSockets() when the session reaches a terminal state.
}

export function nextSeq(sessionId: string): number {
  return ++getOrCreate(sessionId).seq;
}

/**
 * Broadcast a typed event to all WebSocket connections for a session.
 * Stale connections that fail to send are removed silently.
 */
export function broadcast(
  sessionId: string,
  type: WsEvent['type'],
  payload: Record<string, unknown>,
): void {
  const state = sessions.get(sessionId);
  if (!state) return;
  // Always advance seq so reconnecting clients can detect gaps even when
  // the event fires with no clients currently connected.
  const seq = ++state.seq;
  if (state.connections.size === 0) return;
  const msg = JSON.stringify({
    seq,
    session_id: sessionId,
    type,
    ts: new Date().toISOString(),
    payload,
  } as WsEvent);
  for (const ws of state.connections) {
    try {
      ws.send(msg);
    } catch {
      state.connections.delete(ws);
    }
  }
}

/**
 * Close all WebSocket connections for a session and remove its state.
 * Called when a session reaches a terminal state.
 */
export function closeSessionSockets(sessionId: string): void {
  const state = sessions.get(sessionId);
  if (!state) return;
  for (const ws of state.connections) {
    try {
      ws.close(1000, 'Session ended');
    } catch {
      // ignore — connection may already be gone
    }
  }
  sessions.delete(sessionId);
}

