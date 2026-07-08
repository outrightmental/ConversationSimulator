// SPDX-License-Identifier: Apache-2.0
import type {
  HealthResponse,
  ScenarioInfo,
  PackValidationResult,
  SessionCreateRequest,
  SessionCreateResponse,
  SessionStartResponse,
  TurnResponse,
  SessionEndResponse,
  SessionDebriefResponse,
  WsEvent,
  ModelsResponse,
  UseModelRequest,
  UseModelResponse,
  InstallModelRequest,
  InstallModelResponse,
  InstalledModelInfo,
  RegisterGgufRequest,
  RegisterGgufResponse,
} from '@convsim/shared';

export type { HealthResponse };

const BASE = '/api'

export interface PackSummary {
  pack_id: string
  name: string
  scenario_count: number
}

export interface PacksResponse {
  packs: PackSummary[]
  total: number
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
    // convsim-core (Python) returns { error: { code, message } }; the interim
    // convsim-api (TypeScript) returns { code?, message } at the top level.
    // Accept either shape so error text is clean regardless of active backend.
    const json = JSON.parse(text) as {
      message?: string
      code?: string
      error?: { message?: string; code?: string } | string
    }
    // Prefer the top-level message (convsim-api shape, where `error` is a short
    // status string), and fall back to a nested error object (convsim-core shape:
    // { error: { code, message } }).
    let msg = json.message
    let code = json.code
    if (!msg && json.error && typeof json.error === 'object') {
      msg = json.error.message
      code = json.error.code
    }
    if (msg) message = code ? `${code}: ${msg}` : msg
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

async function put<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
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

  packs(): Promise<PacksResponse> {
    return get<PacksResponse>('/packs')
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

export type PackKind = 'official' | 'local-dev'

export interface WorkbenchPack {
  kind: PackKind
  slug: string
  pack_id: string | null
  name: string | null
  editable: boolean
}

export interface FileNode {
  name: string
  path: string
  kind: 'yaml' | 'markdown' | 'text' | 'dir' | 'other'
  children?: FileNode[]
}

export interface WorkbenchValidationIssue {
  severity: 'error' | 'warning'
  rule_id: string
  file: string
  pointer: string
  message: string
  suggested_fix: string
  category?: 'security' | 'schema' | 'structure' | 'syntax'
  line?: number
}

export interface WorkbenchValidation {
  valid: boolean
  errors: WorkbenchValidationIssue[]
  warnings: WorkbenchValidationIssue[]
}

export interface WriteFileResult {
  ok: boolean
  // Present when the backend re-validates the pack after a save (convsim-core).
  // The interim convsim-api backend has no validator and omits this field.
  validation?: WorkbenchValidation | null
}

export interface WsConnection {
  close(): void;
}

export const api = {
  health(): Promise<HealthResponse> {
    return get<HealthResponse>('/health')
  },
  listScenarios(): Promise<ScenarioInfo[]> {
    return get<ScenarioInfo[]>('/scenarios')
  },
  getScenario(scenarioId: string): Promise<ScenarioInfo> {
    return get<ScenarioInfo>(`/scenarios/${scenarioId}`)
  },
  validatePack(packId: string): Promise<PackValidationResult> {
    return post<PackValidationResult>(`/packs/${packId}/validate`)
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
  getModels(): Promise<ModelsResponse> {
    return get<ModelsResponse>('/models')
  },
  useModel(request: UseModelRequest): Promise<UseModelResponse> {
    return post<UseModelResponse>('/models/use', request)
  },
  installModel(request: InstallModelRequest): Promise<InstallModelResponse> {
    return post<InstallModelResponse>('/models/install', request)
  },
  registerGguf(request: RegisterGgufRequest): Promise<RegisterGgufResponse> {
    return post<RegisterGgufResponse>('/models/register-gguf', request)
  },
  getInstallStatus(installId: number): Promise<InstalledModelInfo> {
    return get<InstalledModelInfo>(`/models/install/${installId}`)
  },
  cancelInstall(installId: number): Promise<void> {
    return del(`/models/install/${installId}`)
  },
  startSidecar(model_path: string): Promise<{ state: string; pid: number | null; log_path: string; host: string; port: number }> {
    return post('/sidecar/start', { model_path })
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

  workbench: {
    listPacks(): Promise<WorkbenchPack[]> {
      return get<WorkbenchPack[]>('/workbench/packs')
    },
    listFiles(kind: PackKind, slug: string): Promise<{ tree: FileNode[] }> {
      return get<{ tree: FileNode[] }>(`/workbench/packs/${kind}/${slug}/files`)
    },
    readFile(kind: PackKind, slug: string, filePath: string): Promise<{ content: string; editable: boolean }> {
      return get<{ content: string; editable: boolean }>(
        `/workbench/packs/${kind}/${slug}/file?path=${encodeURIComponent(filePath)}`,
      )
    },
    writeFile(kind: PackKind, slug: string, filePath: string, content: string): Promise<WriteFileResult> {
      return put<WriteFileResult>(
        `/workbench/packs/${kind}/${slug}/file?path=${encodeURIComponent(filePath)}`,
        { content },
      )
    },
    validate(kind: PackKind, slug: string): Promise<WorkbenchValidation> {
      return get<WorkbenchValidation>(`/workbench/packs/${kind}/${slug}/validate`)
    },
    copyToLocal(kind: PackKind, slug: string): Promise<WorkbenchPack> {
      return post<WorkbenchPack>(`/workbench/packs/${kind}/${slug}/copy-to-local`)
    },
  },
}
