// SPDX-License-Identifier: Apache-2.0

// In a packaged Tauri build the web UI is served from tauri://localhost (macOS/Linux)
// or https://tauri.localhost (Windows) — there is no Vite dev-server proxy.  Detect
// this and send API traffic directly to the core service on its fixed port.
// In dev mode (tauri dev), Vite still proxies /api and /ws, so relative paths work.
const _isTauriProduction: boolean =
  typeof window !== 'undefined' &&
  '__TAURI__' in window &&
  (window.location.protocol === 'tauri:' ||
    window.location.hostname === 'tauri.localhost')

const CORE_ORIGIN = 'http://127.0.0.1:7355'

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
  BenchmarkRequest,
  BenchmarkResponse,
  RuntimeSettingsResponse,
  RuntimeSettingsRequest,
  VoicesResponse,
  TtsCacheSizeResponse,
  TtsCacheClearResponse,
} from '@convsim/shared';

export type { HealthResponse };

const BASE = _isTauriProduction ? `${CORE_ORIGIN}/api` : '/api'

export interface PackSummary {
  pack_id: string
  name: string
  scenario_count: number
  pack_root?: string
}

export interface PacksResponse {
  packs: PackSummary[]
  total: number
}

export interface PackDetail {
  pack_id: string
  name: string
  version: string
  scenario_count: number
  pack_root: string
}

export interface ImportPackResponse {
  pack_id: string
  name: string
  version: string
  dest: string
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

export interface SttHealthResponse {
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

  sttHealth(): Promise<SttHealthResponse> {
    return get<SttHealthResponse>('/stt/health')
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

export interface WorkbenchTestSession {
  session_id: string
  state: string
  npc_opening: string
  state_vars: Record<string, number>
}

export interface WorkbenchImportResult extends WorkbenchPack {
  /** Present when the slug was changed to avoid a collision with an existing pack. */
  renamed_from?: string
}

export interface WorkbenchImportValidationError {
  kind: 'validation'
  valid: false
  errors: WorkbenchValidationIssue[]
  warnings: WorkbenchValidationIssue[]
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
  listPacks(): Promise<PacksResponse> {
    return get<PacksResponse>('/packs')
  },
  getPack(packId: string): Promise<PackDetail> {
    return get<PackDetail>(`/packs/${packId}`)
  },
  async importPack(file: File): Promise<ImportPackResponse> {
    const res = await fetch(`${BASE}/packs/import`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/zip' },
      body: file,
    })
    if (!res.ok) throw new Error(await parseErrorMessage(res))
    return res.json() as Promise<ImportPackResponse>
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
  getFolders(): Promise<{ data: string; logs: string; models: string; packs: string; exports: string; cache: string; crash_bundles: string }> {
    return get<{ data: string; logs: string; models: string; packs: string; exports: string; cache: string; crash_bundles: string }>('/privacy/folders')
  },
  clearLocalData(): Promise<{ deleted_sessions: number }> {
    return post<{ deleted_sessions: number }>('/privacy/clear')
  },
  createCrashBundle(): Promise<{ bundle_path: string; notice: string }> {
    return post<{ bundle_path: string; notice: string }>('/diag/crash-bundle')
  },
  deleteSession(sessionId: string): Promise<void> {
    return del(`/sessions/${sessionId}`)
  },
  exportSession(sessionId: string): Promise<unknown> {
    return get<unknown>(`/sessions/${sessionId}/export`)
  },
  async exportTranscriptText(sessionId: string): Promise<{ text: string; filename: string }> {
    const res = await fetch(`${BASE}/sessions/${sessionId}/export/text`)
    if (!res.ok) throw new Error(await parseErrorMessage(res))
    const text = await res.text()
    const disposition = res.headers.get('Content-Disposition') ?? ''
    const match = /filename="([^"]+)"/.exec(disposition)
    const filename = match?.[1] ?? `session-${sessionId}-transcript.md`
    return { text, filename }
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
  benchmarkModel(request: BenchmarkRequest): Promise<BenchmarkResponse> {
    return post<BenchmarkResponse>('/models/benchmark', request)
  },
  getRuntimeSettings(): Promise<RuntimeSettingsResponse> {
    return get<RuntimeSettingsResponse>('/runtime/settings')
  },
  updateRuntimeSettings(request: RuntimeSettingsRequest): Promise<RuntimeSettingsResponse> {
    return put<RuntimeSettingsResponse>('/runtime/settings', request)
  },
  resetRuntimeSettings(): Promise<RuntimeSettingsResponse> {
    return post<RuntimeSettingsResponse>('/runtime/settings/reset')
  },
  listVoices(): Promise<VoicesResponse> {
    return get<VoicesResponse>('/tts/voices')
  },
  getTtsCacheSize(): Promise<TtsCacheSizeResponse> {
    return get<TtsCacheSizeResponse>('/tts/cache/size')
  },
  clearTtsCache(): Promise<TtsCacheClearResponse> {
    return post<TtsCacheClearResponse>('/tts/cache/clear')
  },
  vadHealth(): Promise<VadHealthResponse> {
    return get<VadHealthResponse>('/vad/health')
  },
  connectSession(
    sessionId: string,
    onEvent: (event: WsEvent) => void,
    opts?: { afterSeq?: number },
  ): WsConnection {
    const baseWs = _isTauriProduction
      ? `ws://127.0.0.1:7355/ws/session/${sessionId}`
      : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/session/${sessionId}`
    let url = baseWs
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
    startTestSession(kind: PackKind, slug: string): Promise<WorkbenchTestSession> {
      return post<WorkbenchTestSession>(`/workbench/packs/${kind}/${slug}/test-session`)
    },
    async importPack(
      file: File,
      conflict?: 'rename' | 'overwrite',
    ): Promise<WorkbenchImportResult | WorkbenchImportValidationError> {
      const url = conflict
        ? `${BASE}/workbench/packs/import?conflict=${conflict}`
        : `${BASE}/workbench/packs/import`
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/zip' },
        body: file,
      })
      if (res.status === 422) {
        // A 422 is either a structured validation failure (carrying the full
        // issue list) or a plain error — e.g. a corrupt zip or a zip-slip path,
        // which the backend rejects with a thrown Error (no issue list). Only
        // treat it as a validation result when an errors array is actually
        // present; otherwise surface the message so the UI shows it as an error
        // rather than crashing on an undefined `errors`.
        const data = await res.json().catch(() => null) as
          | { valid?: false; errors?: WorkbenchValidationIssue[]; warnings?: WorkbenchValidationIssue[]; message?: string }
          | null
        if (data && Array.isArray(data.errors)) {
          return { kind: 'validation', valid: false, errors: data.errors, warnings: data.warnings ?? [] }
        }
        throw new Error(data?.message ?? 'Import failed: the uploaded file could not be processed')
      }
      if (!res.ok) throw new Error(await parseErrorMessage(res))
      return res.json() as Promise<WorkbenchImportResult>
    },
    async exportPack(kind: PackKind, slug: string): Promise<{ blob: Blob; filename: string }> {
      const res = await fetch(`${BASE}/workbench/packs/${kind}/${slug}/export`)
      if (res.status === 422) {
        // Validation preflight failed — surface the first error message.
        const data = await res.json() as { errors: WorkbenchValidationIssue[] }
        const first = data.errors[0]
        throw new Error(
          first
            ? `Export blocked: ${first.message} (${first.rule_id})`
            : 'Pack validation failed before export',
        )
      }
      if (!res.ok) throw new Error(await parseErrorMessage(res))
      const blob = await res.blob()
      const disposition = res.headers.get('Content-Disposition') ?? ''
      const match = /filename="([^"]+)"/.exec(disposition)
      const filename = match?.[1] ?? `${slug}.zip`
      return { blob, filename }
    },
  },
}
