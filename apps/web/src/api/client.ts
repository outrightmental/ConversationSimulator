import type {
  HealthResponse,
  ScenarioInfo,
  SessionCreateRequest,
  SessionCreateResponse,
} from '@convsim/shared';

const BASE = '/api';

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health(): Promise<HealthResponse> {
    return apiFetch('/health');
  },

  getScenario(scenarioId: string): Promise<ScenarioInfo> {
    return apiFetch(`/scenarios/${encodeURIComponent(scenarioId)}`);
  },

  createSession(req: SessionCreateRequest): Promise<SessionCreateResponse> {
    return apiFetch('/sessions', { method: 'POST', body: JSON.stringify(req) });
  },
};
