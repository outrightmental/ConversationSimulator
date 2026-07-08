// SPDX-License-Identifier: Apache-2.0
import type {
  HealthResponse as SharedHealthResponse,
  ScenarioInfo,
  SessionCreateRequest,
  SessionCreateResponse,
  SessionStartResponse,
  TurnResponse,
  SessionEndResponse,
  SessionDebriefResponse,
  WsEvent,
} from '@convsim/shared';

const BASE = '/api'

export interface SttHealthInfo {
  worker_id: string
  worker_name: string
  status: 'unavailable' | 'starting' | 'ready' | 'degraded' | 'error'
  model_path?: string | null
  message?: string | null
  checked_at: string
}

export interface HealthResponse {
  status: 'ok' | 'degraded' | 'unavailable'
  version?: string
  stt?: SttHealthInfo
}

export interface SttUploadResponse {
  transcript: string | null
  status: 'ok' | 'unavailable' | 'error'
  language?: string | null
  confidence?: number | null
  duration_ms?: number | null
  processing_ms?: number | null
}

export interface VadCalibrateResponse {
  recommended_threshold: number
  noise_floor: number
  worker_id: string
  status: 'ok' | 'unavailable' | 'error'
  message?: string | null
}

export interface VadHealthResponse {
  worker_id: string
  worker_name: string
  status: 'unavailable' | 'starting' | 'ready' | 'degraded' | 'error'
  model_path?: string | null
  message?: string | null
  checked_at: string
}

async function parseErrorMessage(res: Response): Promise<string> {
  const text = await res.text()
  let message = text || `${res.status} ${res.statusText}`
  try {
    const json = JSON.parse(text) as { message?: string; code?: string }
    if (json.message) message = json.code ? `${json.code}: ${json.message}` : json.message
  } catch {
    // text is not JSON; use as-is
  }
  return message
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(await parseErrorMessage(res))
  return res.json() as Promise<T>
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(await parseErrorMessage(res))
  return res.json() as Promise<T>
}

async function del(path: string): Promise<void> {
  const res = await fetch(`${BASE}${path}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(await parseErrorMessage(res))
}

async function postForm<T>(path: string, body: FormData): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { method: 'POST', body })
  if (!res.ok) {
    throw new Error(await parseErrorMessage(res))
  }
  return res.json() as Promise<T>
}

export const apiClient = {
  health(): Promise<HealthResponse> {
    return get<HealthResponse>('/health')
  },

  uploadAudio(blob: Blob, language?: string): Promise<SttUploadResponse> {
    const ext = blob.type.includes('ogg') ? 'ogg' : 'webm'
    const form = new FormData()
    form.append('audio', blob, `recording.${ext}`)
    if (language) {
      form.append('language', language)
    }
    return postForm<SttUploadResponse>('/stt/upload', form)
  },

  vadHealth(): Promise<VadHealthResponse> {
    return get<VadHealthResponse>('/vad/health')
  },

  vadCalibrate(blob: Blob): Promise<VadCalibrateResponse> {
    const ext = blob.type.includes('ogg') ? 'ogg' : 'webm'
    const form = new FormData()
    form.append('audio', blob, `calibration.${ext}`)
    return postForm<VadCalibrateResponse>('/vad/calibrate', form)
  },
}

export interface WsConnection {
  close(): void;
}

export const api = {
  health(): Promise<SharedHealthResponse> {
    return get<SharedHealthResponse>('/health')
  },
  getScenario(scenarioId: string): Promise<ScenarioInfo> {
    return get<ScenarioInfo>(`/scenarios/${scenarioId}`)
  },
  listSessions(): Promise<{ sessions: SessionCreateResponse[] }> {
    return get<{ sessions: SessionCreateResponse[] }>('/sessions')
  },
  createSession(request: SessionCreateRequest): Promise<SessionCreateResponse> {
    return post<SessionCreateResponse>('/sessions', request)
  },
  getDataFolder(): Promise<{ path: string }> {
    return get<{ path: string }>('/privacy/data-folder')
  },
  clearLocalData(): Promise<{ deleted_sessions: number }> {
    return post<{ deleted_sessions: number }>('/privacy/clear')
  },
  deleteSession(sessionId: string): Promise<void> {
    return del(`/sessions/${sessionId}`)
  },
  exportSession(sessionId: string): Promise<unknown> {
    return get<unknown>(`/sessions/${sessionId}/export`)
  },
  startSession(sessionId: string): Promise<SessionStartResponse> {
    return post<SessionStartResponse>(`/sessions/${sessionId}/start`)
  },
  submitTurn(sessionId: string, content: string): Promise<TurnResponse> {
    return post<TurnResponse>(`/sessions/${sessionId}/turn`, { content })
  },
  endSession(sessionId: string): Promise<SessionEndResponse> {
    return post<SessionEndResponse>(`/sessions/${sessionId}/end`)
  },
  generateDebrief(sessionId: string): Promise<SessionDebriefResponse> {
    return post<SessionDebriefResponse>(`/sessions/${sessionId}/debrief`)
  },
  connectSession(
    sessionId: string,
    onEvent: (event: WsEvent) => void,
    opts?: { afterSeq?: number },
  ): WsConnection {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    let url = `${proto}//${window.location.host}/ws/session/${sessionId}`
    if (opts?.afterSeq != null) url += `?after_seq=${opts.afterSeq}`
    const ws = new WebSocket(url)
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data as string) as WsEvent
      onEvent(data)
    }
    return { close: () => ws.close() }
  },
}
