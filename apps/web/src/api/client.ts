// SPDX-License-Identifier: Apache-2.0
import type {
  HealthResponse as SharedHealthResponse,
  ScenarioInfo,
  SessionCreateRequest,
  SessionCreateResponse,
} from '@convsim/shared';

const BASE = '/api'

export interface HealthResponse {
  status: 'ok' | 'degraded' | 'unavailable'
  version?: string
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}`)
  }
  return res.json() as Promise<T>
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `${res.status} ${res.statusText}`)
  }
  return res.json() as Promise<T>
}

export const apiClient = {
  health(): Promise<HealthResponse> {
    return get<HealthResponse>('/health')
  },
}

export const api = {
  health(): Promise<SharedHealthResponse> {
    return get<SharedHealthResponse>('/health')
  },
  getScenario(scenarioId: string): Promise<ScenarioInfo> {
    return get<ScenarioInfo>(`/scenarios/${scenarioId}`)
  },
  createSession(request: SessionCreateRequest): Promise<SessionCreateResponse> {
    return post<SessionCreateResponse>('/sessions', request)
  },
}
