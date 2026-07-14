import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { api } from './client';
import type { WsSessionStateEvent, WsNpcTokenEvent } from '@convsim/shared';

function mockFetch(status: number, body: unknown) {
  const text = typeof body === 'string' ? body : JSON.stringify(body);
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      statusText: status === 400 ? 'Bad Request' : 'Internal Server Error',
      json: () => Promise.resolve(body),
      text: () => Promise.resolve(text),
    }),
  );
}

const BASE_SESSION = {
  scenario_id: 'behavioral_interview',
  difficulty: 'standard' as const,
  player_role_name: 'Alice',
  language: 'en',
  input_mode: 'text-only' as const,
  tts_enabled: false,
  show_state_meters: false,
  save_transcript: true,
  seed: null,
};

beforeEach(() => {
  vi.unstubAllGlobals();
});

describe('api.createSession — ApiResult return type', () => {
  it('returns ok:true with data on success', async () => {
    mockFetch(201, { session_id: 'sess-1', scenario_id: 'behavioral_interview', state: 'NotStarted', created_at: '' });
    const result = await api.createSession(BASE_SESSION);
    expect(result.ok).toBe(true);
    if (result.ok) expect(result.data.session_id).toBe('sess-1');
  });

  it('returns ok:false with http-error kind and human-readable message on 400', async () => {
    mockFetch(400, {
      statusCode: 400,
      error: 'Bad Request',
      message: 'Unknown scenario_id: nonexistent',
    });
    const result = await api.createSession({ ...BASE_SESSION, scenario_id: 'nonexistent' });
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.kind).toBe('http-error');
      expect(result.error.message).toBe('Unknown scenario_id: nonexistent');
    }
  });

  it('error message does not contain raw JSON (no statusCode field)', async () => {
    mockFetch(400, {
      statusCode: 400,
      error: 'Bad Request',
      message: 'player_role_name cannot be blank',
    });
    const result = await api.createSession({ ...BASE_SESSION, player_role_name: '' });
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.message).toBe('player_role_name cannot be blank');
      expect(result.error.message).not.toContain('"statusCode"');
    }
  });

  it('extracts message from nested convsim-core error object', async () => {
    mockFetch(404, { error: { code: 'PACK_NOT_FOUND', message: 'Pack "ghost" not found' } });
    const result = await api.createSession(BASE_SESSION);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.kind).toBe('http-error');
      expect(result.error.message).toBe('PACK_NOT_FOUND: Pack "ghost" not found');
      expect(result.error.message).not.toContain('{');
    }
  });

  it('falls back to raw text for non-JSON error bodies', async () => {
    mockFetch(500, 'Internal server error (plain text)');
    const result = await api.createSession(BASE_SESSION);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.kind).toBe('http-error');
      expect(result.error.message).toBe('Internal server error (plain text)');
    }
  });
});

// ---------------------------------------------------------------------------
// Content-type / runtime-unreachable guard
// ---------------------------------------------------------------------------

describe('api.createSession — content-type guard', () => {
  it('returns runtime-unreachable when the server returns HTML on a 2xx response', async () => {
    // This is the root-cause scenario: core is down, static server returns index.html
    const html = '<!doctype html><html><body>Loading…</body></html>';
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      statusText: 'OK',
      text: () => Promise.resolve(html),
    }));
    const result = await api.createSession(BASE_SESSION);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.kind).toBe('runtime-unreachable');
      // Parser internals must not leak to the DOM
      expect(result.error.message).not.toContain('Unexpected token');
      expect(result.error.message).not.toContain('<!doctype');
    }
  });

  it('returns runtime-unreachable for any non-JSON 2xx body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      statusText: 'OK',
      text: () => Promise.resolve('not valid json at all'),
    }));
    const result = await api.createSession(BASE_SESSION);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.kind).toBe('runtime-unreachable');
    }
  });

  it('returns runtime-unreachable when an ERROR response carries an HTML body', async () => {
    // A reverse proxy / static server can answer a failing API route with an HTML
    // error page (502/503/504, or a 404 SPA fallback). That raw markup must never
    // become the http-error message — it maps to the same designed degraded state.
    const html = '<!doctype html><html><body>502 Bad Gateway</body></html>';
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 502,
      statusText: 'Bad Gateway',
      text: () => Promise.resolve(html),
    }));
    const result = await api.getScenario('some-id');
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.kind).toBe('runtime-unreachable');
      expect(result.error.message).not.toContain('<!doctype');
      expect(result.error.message).not.toContain('<html');
    }
  });
});

// ---------------------------------------------------------------------------
// Network errors
// ---------------------------------------------------------------------------

describe('api — network errors', () => {
  it('returns ok:false with network kind when fetch rejects (connection refused)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    const result = await api.createSession(BASE_SESSION);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.kind).toBe('network');
    }
  });

  it('returns ok:false with network kind for getScenario when offline', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    const result = await api.getScenario('some-id');
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.kind).toBe('network');
    }
  });
});

// ---------------------------------------------------------------------------
// Empty response bodies
// ---------------------------------------------------------------------------

describe('api — 204 No Content', () => {
  it('returns ok:true for an endpoint that answers 204 with an empty body', async () => {
    // POST /api/setup/outcome is declared status_code=204. Parsing its empty body
    // as JSON throws, which used to surface a bogus runtime-unreachable error.
    mockFetch(204, '');
    const result = await api.recordOnboardingOutcome('demo');
    expect(result.ok).toBe(true);
    if (result.ok) expect(result.data).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// api.getScenario
// ---------------------------------------------------------------------------

describe('api.getScenario', () => {
  it('returns ok:false with http-error on 404', async () => {
    mockFetch(404, {
      statusCode: 404,
      error: 'Not Found',
      message: "Scenario 'nonexistent' not found",
    });
    const result = await api.getScenario('nonexistent');
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.kind).toBe('http-error');
      expect(result.error.message).toBe("Scenario 'nonexistent' not found");
      expect(result.error.message).not.toContain('"statusCode"');
    }
  });

  it('falls back to status text when response body is empty', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      text: () => Promise.resolve(''),
    }));
    const result = await api.getScenario('some_id');
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.kind).toBe('http-error');
      expect(result.error.message).toContain('500');
    }
  });
});

// ---------------------------------------------------------------------------
// api.connectSession — WebSocket client (unchanged behavior)
// ---------------------------------------------------------------------------

interface MockWsInstance {
  url: string;
  onmessage: ((event: { data: string }) => void) | null;
  close: ReturnType<typeof vi.fn>;
  dispatch: (data: unknown) => void;
}

function setupMockWebSocket(): { instances: MockWsInstance[] } {
  const instances: MockWsInstance[] = [];

  class MockWebSocket {
    url: string;
    onmessage: ((event: { data: string }) => void) | null = null;
    close = vi.fn();

    constructor(url: string) {
      this.url = url;
      instances.push(this as unknown as MockWsInstance);
    }

    dispatch(data: unknown) {
      this.onmessage?.({ data: JSON.stringify(data) });
    }
  }

  Object.defineProperty(MockWebSocket.prototype, 'dispatch', {
    value(this: MockWebSocket, data: unknown) {
      this.onmessage?.({ data: JSON.stringify(data) });
    },
    writable: true,
  });

  vi.stubGlobal('WebSocket', MockWebSocket);
  return { instances };
}

describe('api.connectSession', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('constructs the correct WebSocket URL for a session', () => {
    const { instances } = setupMockWebSocket();
    api.connectSession('sess-abc123', () => {});
    expect(instances).toHaveLength(1);
    expect(instances[0]!.url).toContain('/ws/session/sess-abc123');
    expect(instances[0]!.url).not.toContain('after_seq');
  });

  it('appends after_seq to the URL when provided', () => {
    const { instances } = setupMockWebSocket();
    api.connectSession('sess-abc123', () => {}, { afterSeq: 0 });
    expect(instances[0]!.url).toContain('after_seq=0');
  });

  it('calls onEvent with a parsed session.state event', () => {
    const { instances } = setupMockWebSocket();
    const received: unknown[] = [];
    api.connectSession('sess-test', (e) => received.push(e));

    const stateEvent: WsSessionStateEvent = {
      seq: 1,
      session_id: 'sess-test',
      ts: new Date().toISOString(),
      type: 'session.state',
      payload: { state: 'NotStarted', state_vars: {}, ending_type: null },
    };
    instances[0]!.dispatch(stateEvent);

    expect(received).toHaveLength(1);
    expect((received[0] as WsSessionStateEvent).type).toBe('session.state');
    expect((received[0] as WsSessionStateEvent).payload.state).toBe('NotStarted');
  });

  it('calls onEvent with a parsed npc.token event', () => {
    const { instances } = setupMockWebSocket();
    const received: unknown[] = [];
    api.connectSession('sess-test', (e) => received.push(e));

    const tokenEvent: WsNpcTokenEvent = {
      seq: 2,
      session_id: 'sess-test',
      ts: new Date().toISOString(),
      type: 'npc.token',
      payload: { text: 'Hello' },
    };
    instances[0]!.dispatch(tokenEvent);

    expect(received).toHaveLength(1);
    expect((received[0] as WsNpcTokenEvent).payload.text).toBe('Hello');
  });

  it('close() closes the underlying WebSocket', () => {
    const { instances } = setupMockWebSocket();
    const conn = api.connectSession('sess-test', () => {});
    conn.close();
    expect(instances[0]!.close).toHaveBeenCalledOnce();
  });

  it('delivers multiple events in order', () => {
    const { instances } = setupMockWebSocket();
    const types: string[] = [];
    api.connectSession('sess-test', (e) => types.push(e.type));

    instances[0]!.dispatch({ seq: 1, session_id: 'sess-test', ts: '', type: 'session.state', payload: { state: 'NotStarted' } });
    instances[0]!.dispatch({ seq: 2, session_id: 'sess-test', ts: '', type: 'npc.token', payload: { text: 'Hi' } });
    instances[0]!.dispatch({ seq: 3, session_id: 'sess-test', ts: '', type: 'npc.final', payload: { content: 'Hi', emotion: 'neutral', state_delta: {}, event_flags: [] } });

    expect(types).toEqual(['session.state', 'npc.token', 'npc.final']);
  });
});
