import { describe, it, expect, vi, beforeEach } from 'vitest';
import { api } from './client';

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
        difficulty: 'normal',
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
        difficulty: 'normal',
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

  it('falls back to raw text when response is not JSON', async () => {
    mockFetch(500, 'Internal server error (plain text)');

    await expect(
      api.createSession({
        scenario_id: 'behavioral_interview',
        difficulty: 'normal',
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
