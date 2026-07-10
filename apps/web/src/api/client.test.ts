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

beforeEach(() => {
  vi.unstubAllGlobals();
});

describe('api.createSession error handling', () => {
  it('throws with the human-readable message field from a Fastify JSON error', async () => {
    mockFetch(400, {
      statusCode: 400,
      error: 'Bad Request',
      message: 'Unknown scenario_id: nonexistent',
    });

    await expect(
      api.createSession({
        scenario_id: 'nonexistent',
        difficulty: 'standard',
        player_role_name: 'Alice',
        language: 'en',
        input_mode: 'text-only',
        tts_enabled: false,
        show_state_meters: false,
        save_transcript: true,
        seed: null,
      }),
    ).rejects.toThrow('Unknown scenario_id: nonexistent');
  });

  it('does not throw raw JSON string as the error message', async () => {
    mockFetch(400, {
      statusCode: 400,
      error: 'Bad Request',
      message: 'player_role_name cannot be blank',
    });

    let thrownMessage = '';
    try {
      await api.createSession({
        scenario_id: 'behavioral_interview',
        difficulty: 'standard',
        player_role_name: '',
        language: 'en',
        input_mode: 'text-only',
        tts_enabled: false,
        show_state_meters: false,
        save_transcript: true,
        seed: null,
      });
    } catch (e) {
      thrownMessage = e instanceof Error ? e.message : String(e);
    }

    expect(thrownMessage).toBe('player_role_name cannot be blank');
    expect(thrownMessage).not.toContain('"statusCode"');
  });

  it('extracts the message from a convsim-core nested error object', async () => {
    mockFetch(404, { error: { code: 'PACK_NOT_FOUND', message: 'Pack "ghost" not found' } });

    let thrownMessage = '';
    try {
      await api.createSession({
        scenario_id: 'behavioral_interview',
        difficulty: 'standard',
        player_role_name: 'Alice',
        language: 'en',
        input_mode: 'text-only',
        tts_enabled: false,
        show_state_meters: false,
        save_transcript: true,
        seed: null,
      });
    } catch (e) {
      thrownMessage = e instanceof Error ? e.message : String(e);
    }

    expect(thrownMessage).toBe('PACK_NOT_FOUND: Pack "ghost" not found');
    expect(thrownMessage).not.toContain('{');
  });

  it('falls back to raw text when response is not JSON', async () => {
    mockFetch(500, 'Internal server error (plain text)');

    await expect(
      api.createSession({
        scenario_id: 'behavioral_interview',
        difficulty: 'standard',
        player_role_name: 'Alice',
        language: 'en',
        input_mode: 'text-only',
        tts_enabled: false,
        show_state_meters: false,
        save_transcript: true,
        seed: null,
      }),
    ).rejects.toThrow('Internal server error (plain text)');
  });
});

// ---------------------------------------------------------------------------
// api.connectSession — WebSocket client
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

  // Patch MockWebSocket instances with dispatch helper
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

describe('api.getScenario error handling', () => {
  it('throws with the human-readable message field from a Fastify JSON error', async () => {
    mockFetch(404, {
      statusCode: 404,
      error: 'Not Found',
      message: "Scenario 'nonexistent' not found",
    });

    await expect(api.getScenario('nonexistent')).rejects.toThrow(
      "Scenario 'nonexistent' not found",
    );
  });

  it('does not throw raw JSON string as the error message', async () => {
    mockFetch(404, {
      statusCode: 404,
      error: 'Not Found',
      message: "Scenario 'nonexistent' not found",
    });

    let thrownMessage = '';
    try {
      await api.getScenario('nonexistent');
    } catch (e) {
      thrownMessage = e instanceof Error ? e.message : String(e);
    }

    expect(thrownMessage).not.toContain('"statusCode"');
  });

  it('falls back to status text when response is not JSON', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        text: () => Promise.resolve(''),
      }),
    );

    await expect(api.getScenario('some_id')).rejects.toThrow('500 Internal Server Error');
  });
});
