// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { buildApp } from '../index.js';
import { resetDb } from '../db.js';
import { broadcast } from '../ws/session-events.js';
import type { FastifyInstance } from 'fastify';
import type {
  SessionCreateResponse,
  WsEvent,
  WsSessionStateEvent,
  WsNpcFinalEvent,
  WsNpcTokenEvent,
} from '@convsim/shared';

let app: FastifyInstance;

const validRequest = {
  scenario_id: 'behavioral_interview',
  difficulty: 'standard',
  player_role_name: 'Alice',
  language: 'en',
  input_mode: 'text-only',
  tts_enabled: false,
  show_state_meters: false,
  save_transcript: true,
  seed: null,
};

beforeEach(async () => {
  resetDb();
  app = await buildApp();
  await app.ready();
});

afterEach(async () => {
  await app.close();
});

// ---------------------------------------------------------------------------
// WsConn — in-process WebSocket connection helper
//
// `injectWS` delivers the first server message SYNCHRONOUSLY during the
// WebSocket upgrade, before the Promise resolves. Listeners registered in
// `onInit` (fires before the upgrade) capture every message without any race.
// `take(n)` dequeues n buffered events, waiting asynchronously if needed.
// ---------------------------------------------------------------------------

interface WsConn {
  close: () => void;
  take: (n: number) => Promise<WsEvent[]>;
}

function connectWs(path: string): Promise<WsConn> {
  const pending: WsEvent[] = [];
  const waiters: Array<{ n: number; resolve: (e: WsEvent[]) => void; reject: (e: Error) => void }> = [];

  function flush() {
    while (waiters.length > 0 && pending.length >= waiters[0]!.n) {
      const { n, resolve } = waiters.shift()!;
      resolve(pending.splice(0, n));
    }
  }

  let resolveConn!: (c: WsConn) => void;
  let rejectConn!: (e: Error) => void;
  const connP = new Promise<WsConn>((res, rej) => {
    resolveConn = res;
    rejectConn = rej;
  });

  app.injectWS(path, undefined, {
    onInit: (ws) => {
      ws.on('message', (data: Buffer | string) => {
        pending.push(JSON.parse(data.toString()) as WsEvent);
        flush();
      });
      ws.on('error', (err: Error) => {
        waiters.forEach((w) => w.reject(err));
        waiters.length = 0;
        rejectConn(err);
      });
      ws.on('close', () => {
        // Resolve any remaining waiters with whatever has been buffered.
        flush();
        for (const w of waiters) w.resolve(pending.splice(0));
        waiters.length = 0;
      });
    },
    onOpen: (ws) => {
      resolveConn({
        close: () => {
          try { ws.terminate(); } catch { /* already closed */ }
        },
        take: (n: number) => {
          if (pending.length >= n) return Promise.resolve(pending.splice(0, n));
          return new Promise((res, rej) => waiters.push({ n, resolve: res, reject: rej }));
        },
      });
    },
  }).catch(rejectConn);

  return connP;
}

/** Create a session via the in-process HTTP handler. */
async function createSession(): Promise<string> {
  const res = await app.inject({
    method: 'POST',
    url: '/api/sessions',
    payload: validRequest,
  });
  return res.json<SessionCreateResponse>().session_id;
}

/**
 * Create a session and start it. The WebSocket connection should be open
 * BEFORE calling this if you want to receive the start events; otherwise the
 * session will simply be in PlayerTurnListening when you connect.
 */
async function startSession(session_id: string): Promise<void> {
  await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/start` });
}

// ---------------------------------------------------------------------------
// Connection and initial state handshake
// ---------------------------------------------------------------------------

describe('GET /ws/session/:session_id', () => {
  it('sends a session.state event on connect', async () => {
    const session_id = await createSession();
    const conn = await connectWs(`/ws/session/${session_id}`);
    const [event] = await conn.take(1);
    conn.close();

    expect(event.type).toBe('session.state');
    expect(event.session_id).toBe(session_id);
    expect(typeof event.seq).toBe('number');
    expect(typeof event.ts).toBe('string');
    expect((event as WsSessionStateEvent).payload.state).toBe('NotStarted');
  });

  it('initial session.state includes state_vars object', async () => {
    const session_id = await createSession();
    const conn = await connectWs(`/ws/session/${session_id}`);
    const [event] = await conn.take(1);
    conn.close();

    expect(typeof (event as WsSessionStateEvent).payload.state_vars).toBe('object');
  });

  it('sends an error event for an unknown session', async () => {
    const conn = await connectWs('/ws/session/sess-doesnotexist');
    const [event] = await conn.take(1);
    conn.close();

    expect(event.type).toBe('error');
    expect((event as { payload: { code: string } }).payload.code).toBe('SESSION_NOT_FOUND');
  });

  it('sequence number on initial event is 1', async () => {
    const session_id = await createSession();
    const conn = await connectWs(`/ws/session/${session_id}`);
    const [event] = await conn.take(1);
    conn.close();

    expect(event.seq).toBe(1);
  });

  it('sequence numbers increment monotonically across multiple events', async () => {
    const session_id = await createSession();
    const conn = await connectWs(`/ws/session/${session_id}`);
    await conn.take(1); // initial session.state

    // Start session: emits session.state + npc.final (2 events)
    await startSession(session_id);
    await conn.take(2);

    // Submit a turn: emits npc.token + npc.final + session.state (3 events)
    await app.inject({
      method: 'POST',
      url: `/api/sessions/${session_id}/turn`,
      payload: { content: 'Hello!' },
    });
    const turnEvents = await conn.take(3);
    conn.close();

    const seqs = turnEvents.map((e) => e.seq);
    for (let i = 1; i < seqs.length; i++) {
      expect(seqs[i]).toBeGreaterThan(seqs[i - 1]!);
    }
  });
});

// ---------------------------------------------------------------------------
// Events emitted by the text turn loop
// ---------------------------------------------------------------------------

describe('WebSocket events from the text loop', () => {
  it('emits session.state and npc.final after /start', async () => {
    const session_id = await createSession();
    const conn = await connectWs(`/ws/session/${session_id}`);
    await conn.take(1); // initial session.state

    await startSession(session_id);
    const events = await conn.take(2);
    conn.close();

    const stateEvt = events.find((e) => e.type === 'session.state') as WsSessionStateEvent | undefined;
    expect(stateEvt?.payload.state).toBe('PlayerTurnListening');
    expect(stateEvt?.payload.state_vars).toBeDefined();

    const npcEvt = events.find((e) => e.type === 'npc.final') as WsNpcFinalEvent | undefined;
    expect(npcEvt).toBeDefined();
    expect(typeof npcEvt!.payload.content).toBe('string');
    expect(npcEvt!.payload.content.length).toBeGreaterThan(0);
  });

  it('emits npc.token and npc.final after a player turn', async () => {
    const session_id = await createSession();
    const conn = await connectWs(`/ws/session/${session_id}`);
    await conn.take(1); // initial state

    // Start the session — emits 2 events (session.state + npc.final)
    await startSession(session_id);
    await conn.take(2);

    // Submit a turn — emits npc.token + npc.final + session.state (3 events)
    await app.inject({
      method: 'POST',
      url: `/api/sessions/${session_id}/turn`,
      payload: { content: 'Hello there.' },
    });
    const events = await conn.take(3);
    conn.close();

    const tokenEvt = events.find((e) => e.type === 'npc.token') as WsNpcTokenEvent | undefined;
    expect(tokenEvt).toBeDefined();
    expect(typeof tokenEvt!.payload.text).toBe('string');

    const finalEvt = events.find((e) => e.type === 'npc.final') as WsNpcFinalEvent | undefined;
    expect(finalEvt).toBeDefined();
    expect(typeof finalEvt!.payload.content).toBe('string');
    expect(Array.isArray(finalEvt!.payload.event_flags)).toBe(true);
    expect(typeof finalEvt!.payload.state_delta).toBe('object');
  });

  it('session.state after turn reflects PlayerTurnListening and state_vars', async () => {
    const session_id = await createSession();
    const conn = await connectWs(`/ws/session/${session_id}`);
    await conn.take(1);

    await startSession(session_id);
    await conn.take(2);

    await app.inject({
      method: 'POST',
      url: `/api/sessions/${session_id}/turn`,
      payload: { content: 'Test turn.' },
    });
    const events = await conn.take(3);
    conn.close();

    const stateEvt = events.find((e) => e.type === 'session.state') as WsSessionStateEvent | undefined;
    expect(stateEvt).toBeDefined();
    expect(stateEvt!.payload.state).toBe('PlayerTurnListening');
    expect(typeof stateEvt!.payload.state_vars).toBe('object');
  });

  it('emits session.state with Ended when session is ended via /end', async () => {
    const session_id = await createSession();
    const conn = await connectWs(`/ws/session/${session_id}`);
    await conn.take(1);

    await startSession(session_id);
    await conn.take(2); // consume start events

    await app.inject({ method: 'POST', url: `/api/sessions/${session_id}/end` });
    // End emits session.state with Ended state
    const [stateEvt] = await conn.take(1);

    const payload = (stateEvt as WsSessionStateEvent).payload;
    expect(payload.state).toBe('Ended');
    expect(typeof payload.state_vars).toBe('object');
  });

  it('npc.token text matches npc.final content', async () => {
    const session_id = await createSession();
    const conn = await connectWs(`/ws/session/${session_id}`);
    await conn.take(1);
    await startSession(session_id);
    await conn.take(2);

    await app.inject({
      method: 'POST',
      url: `/api/sessions/${session_id}/turn`,
      payload: { content: 'What is your name?' },
    });
    const events = await conn.take(3);
    conn.close();

    const tokenEvt = events.find((e) => e.type === 'npc.token') as WsNpcTokenEvent | undefined;
    const finalEvt = events.find((e) => e.type === 'npc.final') as WsNpcFinalEvent | undefined;
    expect(tokenEvt!.payload.text).toBe(finalEvt!.payload.content);
  });
});

// ---------------------------------------------------------------------------
// Reconnect / replay
// ---------------------------------------------------------------------------

describe('reconnect and event replay', () => {
  it('seq is monotonically increasing across reconnects — does not reset to 1', async () => {
    const session_id = await createSession();

    // First connection: receive initial state (seq=1) and start events (seq=2,3).
    const conn1 = await connectWs(`/ws/session/${session_id}`);
    await conn1.take(1); // initial state, seq=1
    await startSession(session_id);
    await conn1.take(2); // start events, seq=2,3
    conn1.close();

    // Reconnect without replay — the initial session.state must have seq > 3,
    // proving the counter survived the disconnect rather than resetting to 1.
    const conn2 = await connectWs(`/ws/session/${session_id}`);
    const [reconnectEvt] = await conn2.take(1);
    conn2.close();

    expect(reconnectEvt.seq).toBeGreaterThan(3);
  });

  it('reconnecting without after_seq receives current session.state only', async () => {
    const session_id = await createSession();

    // First connection — start the session while connected.
    const conn1 = await connectWs(`/ws/session/${session_id}`);
    await conn1.take(1); // initial state
    await startSession(session_id);
    await conn1.take(2); // start events
    conn1.close();

    // Submit a turn while disconnected.
    await app.inject({
      method: 'POST',
      url: `/api/sessions/${session_id}/turn`,
      payload: { content: 'Turn while disconnected.' },
    });

    // Reconnect without replay — should receive exactly one session.state.
    const conn2 = await connectWs(`/ws/session/${session_id}`);
    const [reconnectEvt] = await conn2.take(1);
    conn2.close();

    expect(reconnectEvt.type).toBe('session.state');
    expect((reconnectEvt as WsSessionStateEvent).payload.state).toBe('PlayerTurnListening');
  });

  it('replays recent durable events when after_seq=0 is provided', async () => {
    const session_id = await createSession();

    // Start the session and submit a turn to create durable session_events rows.
    await startSession(session_id);
    await app.inject({
      method: 'POST',
      url: `/api/sessions/${session_id}/turn`,
      payload: { content: 'First turn.' },
    });

    // Reconnect with after_seq=0 to replay all events.
    const conn = await connectWs(`/ws/session/${session_id}?after_seq=0`);
    // Expect: initial session.state + replayed npc.final (opening) + replayed npc.final (turn)
    const events = await conn.take(3);
    conn.close();

    expect(events[0]!.type).toBe('session.state');
    expect(events.some((e) => e.type === 'npc.final')).toBe(true);
  });

  it('reconnect does not duplicate persisted turns', async () => {
    const session_id = await createSession();
    await startSession(session_id);
    await app.inject({
      method: 'POST',
      url: `/api/sessions/${session_id}/turn`,
      payload: { content: 'Single turn.' },
    });

    // Reconnect with after_seq=0 — replay should include at most one npc.final per turn.
    const conn = await connectWs(`/ws/session/${session_id}?after_seq=0`);
    // session.state + npc.final (opening) + npc.final (one turn) = 3 events
    const events = await conn.take(3);
    conn.close();

    const npcFinals = events.filter((e) => e.type === 'npc.final');
    // At most 2 npc.final events (opening + one turn), never more.
    expect(npcFinals.length).toBeLessThanOrEqual(2);
  });

  it('non-zero after_seq is treated as no replay — receives only current session.state', async () => {
    const session_id = await createSession();
    await startSession(session_id);
    await app.inject({
      method: 'POST',
      url: `/api/sessions/${session_id}/turn`,
      payload: { content: 'Some turn.' },
    });

    // after_seq=1 (non-zero) should NOT trigger replay — only the initial state.
    const conn = await connectWs(`/ws/session/${session_id}?after_seq=1`);
    await conn.take(1); // consume initial session.state

    // Request more events. Closing the socket causes take() to resolve with
    // whatever is buffered — an empty array proves no replay events were sent.
    const extraP = conn.take(5);
    conn.close();
    const extra = await extraP;

    expect(extra.length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Error surfacing
// ---------------------------------------------------------------------------

describe('error surfacing', () => {
  it('surfaces a typed error event for unknown session', async () => {
    const conn = await connectWs('/ws/session/sess-unknown');
    const [event] = await conn.take(1);
    conn.close();

    expect(event.type).toBe('error');
    expect(event.session_id).toBe('sess-unknown');
    expect((event as { payload: { code: string } }).payload.code).toBe('SESSION_NOT_FOUND');
  });

  it('server remains healthy after a bad WebSocket connection', async () => {
    const conn = await connectWs('/ws/session/sess-unknown');
    await conn.take(1); // error event
    conn.close();

    const healthRes = await app.inject({ method: 'GET', url: '/api/health' });
    expect(healthRes.statusCode).toBe(200);
  });
});

// ---------------------------------------------------------------------------
// Multi-client fan-out
// ---------------------------------------------------------------------------

describe('multi-client fan-out', () => {
  it('two clients connected to the same session both receive turn events', async () => {
    const session_id = await createSession();

    const conn1 = await connectWs(`/ws/session/${session_id}`);
    const conn2 = await connectWs(`/ws/session/${session_id}`);

    // Both clients consume their initial session.state event.
    await Promise.all([conn1.take(1), conn2.take(1)]);

    // Start the session — both clients should receive session.state + npc.final.
    await startSession(session_id);
    const [start1, start2] = await Promise.all([conn1.take(2), conn2.take(2)]);
    expect(start1.some((e) => e.type === 'npc.final')).toBe(true);
    expect(start2.some((e) => e.type === 'npc.final')).toBe(true);

    // Submit a turn — both clients receive npc.token + npc.final + session.state.
    await app.inject({
      method: 'POST',
      url: `/api/sessions/${session_id}/turn`,
      payload: { content: 'Hello from two clients.' },
    });
    const [turn1, turn2] = await Promise.all([conn1.take(3), conn2.take(3)]);
    conn1.close();
    conn2.close();

    expect(turn1.some((e) => e.type === 'npc.final')).toBe(true);
    expect(turn2.some((e) => e.type === 'npc.final')).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Conditional event types (scenario.state_delta, scenario.event, safety.redirect)
//
// The fake NPC always returns empty state_delta / event_flags, so these
// broadcasts are never triggered through the HTTP turn handler in tests.
// We exercise them by calling broadcast() directly to prove the events are
// delivered and well-formed on the wire.
// ---------------------------------------------------------------------------

describe('conditional broadcast event types', () => {
  it('delivers scenario.state_delta to connected clients', async () => {
    const session_id = await createSession();
    const conn = await connectWs(`/ws/session/${session_id}`);
    await conn.take(1); // initial session.state

    broadcast(session_id, 'scenario.state_delta', {
      delta: { trust: 5 },
      state_vars: { trust: 55, patience: 75, pressure: 25, rapport: 50, openness: 50, objective_progress: 0 },
    });

    const [evt] = await conn.take(1);
    conn.close();

    expect(evt.type).toBe('scenario.state_delta');
    expect(evt.session_id).toBe(session_id);
    expect(typeof evt.seq).toBe('number');
  });

  it('delivers scenario.event to connected clients', async () => {
    const session_id = await createSession();
    const conn = await connectWs(`/ws/session/${session_id}`);
    await conn.take(1); // initial session.state

    broadcast(session_id, 'scenario.event', { flags: ['rapport_milestone'] });

    const [evt] = await conn.take(1);
    conn.close();

    expect(evt.type).toBe('scenario.event');
    expect(evt.session_id).toBe(session_id);
  });

  it('delivers safety.redirect to connected clients', async () => {
    const session_id = await createSession();
    const conn = await connectWs(`/ws/session/${session_id}`);
    await conn.take(1); // initial session.state

    broadcast(session_id, 'safety.redirect', { reason: 'Test safety redirect' });

    const [evt] = await conn.take(1);
    conn.close();

    expect(evt.type).toBe('safety.redirect');
  });
});

// ---------------------------------------------------------------------------
// Seq counter advances when events fire with no clients connected
// ---------------------------------------------------------------------------

describe('seq gap detection during disconnection', () => {
  it('seq advances for broadcasts that occur while no client is connected', async () => {
    const session_id = await createSession();

    // Connect, observe initial state (seq=1) and start events (seq=2, seq=3).
    const conn1 = await connectWs(`/ws/session/${session_id}`);
    await conn1.take(1);
    await startSession(session_id);
    const [, lastStartEvt] = await conn1.take(2);
    conn1.close();

    // Submit a turn while disconnected — 3 broadcasts (npc.token, npc.final,
    // session.state) should still advance the seq counter.
    await app.inject({
      method: 'POST',
      url: `/api/sessions/${session_id}/turn`,
      payload: { content: 'Turn while disconnected.' },
    });

    // Reconnect: the initial session.state must have a seq greater than
    // (lastStartEvt.seq + 1), proving the counter advanced during disconnection.
    const conn2 = await connectWs(`/ws/session/${session_id}`);
    const [reconnectEvt] = await conn2.take(1);
    conn2.close();

    expect(reconnectEvt.seq).toBeGreaterThan(lastStartEvt!.seq + 1);
  });
});
