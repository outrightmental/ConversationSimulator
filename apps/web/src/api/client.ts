// SPDX-License-Identifier: Apache-2.0

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

export const apiClient = {
  health(): Promise<HealthResponse> {
    return get<HealthResponse>('/health')
  },
}
