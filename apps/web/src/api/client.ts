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
  BackchannelsResponse,
  LogbookProfile,
  LogbookExport,
  PreflightResponse,
  SetupInstallJob,
} from '@convsim/shared';

export type { HealthResponse };
export type { ApiError, ApiResult } from './errors';

import type { ApiError, ApiResult } from './errors';

const BASE = _isTauriProduction ? `${CORE_ORIGIN}/api` : '/api'

export interface CloudSettings {
  /** Last model ID selected by the user. The only field Steam Cloud syncs. */
  last_model_id: string | null
}

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

export interface RelationshipRecapSummary {
  npc_id: string
  pack_id: string
  session_count: number
  updated_at: string
  key_observations: string[]
  player_style_tags: string[]
  last_outcome: string | null
  last_session_at: string | null
}

export interface SttHealthResponse {
  worker_id: string
  worker_name: string
  status: 'unavailable' | 'starting' | 'ready' | 'degraded' | 'error'
  model_path?: string | null
  message?: string | null
  checked_at: string
}

const HTML_ERROR: Omit<ApiError, 'status'> = {
  kind: 'runtime-unreachable',
  message: 'API returned HTML instead of JSON — the local runtime is not running.',
}

// Turn an already-read error body into a clean message. Never returns HTML or
// parser internals — an HTML body is handled upstream in errorFromResponse and
// never reaches here.
function parseErrorText(text: string, res: Response): string {
  const fallback = text || `${res.status} ${res.statusText}`
  try {
    // convsim-core (Python) returns { error: { code, message } }; the interim
    // convsim-api (TypeScript) returns { code?, message } at the top level;
    // FastAPI standard errors (404, 422, etc.) return { detail: string }.
    // Accept all shapes so error text is clean regardless of active backend.
    const json = JSON.parse(text) as {
      message?: string
      code?: string
      detail?: string | unknown[]
      error?: { message?: string; code?: string } | string
    }
    let msg = json.message
    let code = json.code
    if (!msg && json.error && typeof json.error === 'object') {
      msg = json.error.message
      code = json.error.code
    }
    // FastAPI uses { detail: string } for standard HTTP errors (404, 500, etc.)
    if (!msg && typeof json.detail === 'string') {
      msg = json.detail
    }
    if (msg) return code ? `${code}: ${msg}` : msg
  } catch {
    // text is not JSON; use as-is
  }
  return fallback
}

// Build an ApiError for a non-2xx response. Reads the body once and applies the
// same content-type guard as the success path: an HTML error page (a static
// server or reverse proxy answering an API route while core is down — which can
// arrive with any status, not just 2xx) maps to runtime-unreachable so the raw
// "<!doctype …>" markup can never reach the DOM.
async function errorFromResponse(res: Response): Promise<ApiError> {
  let text = ''
  try { text = await res.text() } catch { /* ignore */ }
  if (text.trimStart().startsWith('<')) {
    return { ...HTML_ERROR, status: res.status }
  }
  return { kind: 'http-error', message: parseErrorText(text, res), status: res.status }
}

// Guard: reads the body as text, then JSON.parses it.  If the server returned
// HTML (static server answering an API route while core is down), the parse
// fails and we return runtime-unreachable instead of letting the raw parser
// error or "<html>" content reach the DOM.
async function handleResponse<T>(res: Response): Promise<ApiResult<T>> {
  if (!res.ok) {
    return { ok: false, error: await errorFromResponse(res) }
  }
  let text = ''
  try { text = await res.text() } catch { /* ignore */ }
  let data: T
  try {
    data = JSON.parse(text) as T
  } catch {
    const isHtml = text.trimStart().startsWith('<')
    return {
      ok: false,
      error: {
        kind: 'runtime-unreachable',
        message: isHtml
          ? HTML_ERROR.message
          : 'API returned a non-JSON response — the local runtime may not be running.',
        status: res.status,
      },
    }
  }
  return { ok: true, data }
}

async function get<T>(path: string): Promise<ApiResult<T>> {
  try {
    const res = await fetch(`${BASE}${path}`)
    return handleResponse<T>(res)
  } catch (err) {
    return { ok: false, error: { kind: 'network', message: err instanceof Error ? err.message : 'Network error' } }
  }
}

async function post<T>(path: string, body?: unknown): Promise<ApiResult<T>> {
  try {
    const res = await fetch(`${BASE}${path}`, {
      method: 'POST',
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
    return handleResponse<T>(res)
  } catch (err) {
    return { ok: false, error: { kind: 'network', message: err instanceof Error ? err.message : 'Network error' } }
  }
}

async function put<T>(path: string, body: unknown): Promise<ApiResult<T>> {
  try {
    const res = await fetch(`${BASE}${path}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    return handleResponse<T>(res)
  } catch (err) {
    return { ok: false, error: { kind: 'network', message: err instanceof Error ? err.message : 'Network error' } }
  }
}

async function del(path: string): Promise<ApiResult<undefined>> {
  try {
    const res = await fetch(`${BASE}${path}`, { method: 'DELETE' })
    if (!res.ok) {
      return { ok: false, error: await errorFromResponse(res) }
    }
    return { ok: true, data: undefined }
  } catch (err) {
    return { ok: false, error: { kind: 'network', message: err instanceof Error ? err.message : 'Network error' } }
  }
}

async function postForm<T>(path: string, body: FormData): Promise<ApiResult<T>> {
  try {
    const res = await fetch(`${BASE}${path}`, { method: 'POST', body })
    return handleResponse<T>(res)
  } catch (err) {
    return { ok: false, error: { kind: 'network', message: err instanceof Error ? err.message : 'Network error' } }
  }
}

export const apiClient = {
  health(): Promise<ApiResult<HealthResponse>> {
    return get<HealthResponse>('/health')
  },

  packs(): Promise<ApiResult<PacksResponse>> {
    return get<PacksResponse>('/packs')
  },

  reseedOfficialPacks(): Promise<ApiResult<{ seeded: number }>> {
    return post<{ seeded: number }>('/packs/reseed')
  },

  uploadAudio(blob: Blob, language?: string): Promise<ApiResult<SttUploadResponse>> {
    const ext = blob.type.includes('ogg') ? 'ogg' : 'webm'
    const form = new FormData()
    form.append('audio', blob, `recording.${ext}`)
    if (language) {
      form.append('language', language)
    }
    return postForm<SttUploadResponse>('/stt/upload', form)
  },

  sttHealth(): Promise<ApiResult<SttHealthResponse>> {
    return get<SttHealthResponse>('/stt/health')
  },

  vadHealth(): Promise<ApiResult<VadHealthResponse>> {
    return get<VadHealthResponse>('/vad/health')
  },

  vadCalibrate(blob: Blob): Promise<ApiResult<VadCalibrateResponse>> {
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
  health(): Promise<ApiResult<HealthResponse>> {
    return get<HealthResponse>('/health')
  },
  listScenarios(): Promise<ApiResult<ScenarioInfo[]>> {
    return get<ScenarioInfo[]>('/scenarios')
  },
  getScenario(scenarioId: string): Promise<ApiResult<ScenarioInfo>> {
    return get<ScenarioInfo>(`/scenarios/${scenarioId}`)
  },
  listPacks(): Promise<ApiResult<PacksResponse>> {
    return get<PacksResponse>('/packs')
  },
  getPack(packId: string): Promise<ApiResult<PackDetail>> {
    return get<PackDetail>(`/packs/${packId}`)
  },
  async importPack(file: File): Promise<ApiResult<ImportPackResponse>> {
    try {
      const res = await fetch(`${BASE}/packs/import`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/zip' },
        body: file,
      })
      return handleResponse<ImportPackResponse>(res)
    } catch (err) {
      return { ok: false, error: { kind: 'network', message: err instanceof Error ? err.message : 'Network error' } }
    }
  },
  validatePack(packId: string): Promise<ApiResult<PackValidationResult>> {
    return post<PackValidationResult>(`/packs/${packId}/validate`)
  },
  listSessions(): Promise<ApiResult<{ sessions: SessionCreateResponse[] }>> {
    return get<{ sessions: SessionCreateResponse[] }>('/sessions')
  },
  getLogbookProfile(): Promise<ApiResult<LogbookProfile>> {
    return get<LogbookProfile>('/logbook/profile')
  },
  exportLogbook(): Promise<ApiResult<LogbookExport>> {
    return get<LogbookExport>('/logbook/export')
  },
  createSession(request: SessionCreateRequest): Promise<ApiResult<SessionCreateResponse>> {
    return post<SessionCreateResponse>('/sessions', request)
  },
  getDataFolder(): Promise<ApiResult<{ path: string }>> {
    return get<{ path: string }>('/privacy/data-folder')
  },
  getFolders(): Promise<ApiResult<{ data: string; logs: string; models: string; packs: string; exports: string; cache: string; crash_bundles: string }>> {
    return get<{ data: string; logs: string; models: string; packs: string; exports: string; cache: string; crash_bundles: string }>('/privacy/folders')
  },
  clearLocalData(): Promise<ApiResult<{ deleted_sessions: number }>> {
    return post<{ deleted_sessions: number }>('/privacy/clear')
  },
  createCrashBundle(): Promise<ApiResult<{ bundle_path: string; notice: string }>> {
    return post<{ bundle_path: string; notice: string }>('/diag/crash-bundle')
  },
  createBetaReport(includeSessionMetadata: boolean): Promise<ApiResult<{ bundle_path: string; manifest: string[]; notice: string }>> {
    return post<{ bundle_path: string; manifest: string[]; notice: string }>('/diag/beta-report', { include_session_metadata: includeSessionMetadata })
  },
  preflight(): Promise<ApiResult<PreflightResponse>> {
    return get<PreflightResponse>('/preflight')
  },
  deleteSession(sessionId: string): Promise<ApiResult<undefined>> {
    return del(`/sessions/${sessionId}`)
  },
  listRelationshipMemory(): Promise<ApiResult<{ recaps: RelationshipRecapSummary[]; total: number }>> {
    return get<{ recaps: RelationshipRecapSummary[]; total: number }>('/relationship-memory')
  },
  deleteRelationshipMemory(npcId: string, packId: string): Promise<ApiResult<undefined>> {
    return del(`/relationship-memory/${encodeURIComponent(npcId)}/${encodeURIComponent(packId)}`)
  },
  clearAllRelationshipMemory(): Promise<ApiResult<undefined>> {
    return del('/relationship-memory')
  },
  exportSession(sessionId: string): Promise<ApiResult<unknown>> {
    return get<unknown>(`/sessions/${sessionId}/export`)
  },
  async exportTranscriptText(sessionId: string): Promise<ApiResult<{ text: string; filename: string }>> {
    try {
      const res = await fetch(`${BASE}/sessions/${sessionId}/export/text`)
      if (!res.ok) {
        return { ok: false, error: await errorFromResponse(res) }
      }
      const text = await res.text()
      const disposition = res.headers.get('Content-Disposition') ?? ''
      const match = /filename="([^"]+)"/.exec(disposition)
      const filename = match?.[1] ?? `session-${sessionId}-transcript.md`
      return { ok: true, data: { text, filename } }
    } catch (err) {
      return { ok: false, error: { kind: 'network', message: err instanceof Error ? err.message : 'Network error' } }
    }
  },
  startSession(sessionId: string): Promise<ApiResult<SessionStartResponse>> {
    return post<SessionStartResponse>(`/sessions/${sessionId}/start`)
  },
  submitTurn(sessionId: string, content: string, barged_in?: boolean): Promise<ApiResult<TurnResponse>> {
    return post<TurnResponse>(`/sessions/${sessionId}/turn`, { content, barged_in: barged_in ?? false })
  },
  endSession(sessionId: string): Promise<ApiResult<SessionEndResponse>> {
    return post<SessionEndResponse>(`/sessions/${sessionId}/end`)
  },
  generateDebrief(sessionId: string): Promise<ApiResult<SessionDebriefResponse>> {
    return post<SessionDebriefResponse>(`/sessions/${sessionId}/debrief`)
  },
  getModels(): Promise<ApiResult<ModelsResponse>> {
    return get<ModelsResponse>('/models')
  },
  useModel(request: UseModelRequest): Promise<ApiResult<UseModelResponse>> {
    return post<UseModelResponse>('/models/use', request)
  },
  installModel(request: InstallModelRequest): Promise<ApiResult<InstallModelResponse>> {
    return post<InstallModelResponse>('/models/install', request)
  },
  registerGguf(request: RegisterGgufRequest): Promise<ApiResult<RegisterGgufResponse>> {
    return post<RegisterGgufResponse>('/models/register-gguf', request)
  },
  getInstallStatus(installId: number): Promise<ApiResult<InstalledModelInfo>> {
    return get<InstalledModelInfo>(`/models/install/${installId}`)
  },
  cancelInstall(installId: number): Promise<ApiResult<undefined>> {
    return del(`/models/install/${installId}`)
  },
  startSidecar(model_path: string): Promise<ApiResult<{ state: string; pid: number | null; log_path: string; host: string; port: number }>> {
    return post('/sidecar/start', { model_path })
  },
  getSidecarStatus(): Promise<ApiResult<{ state: string; pid: number | null; model_path: string | null; error: string | null; log_path: string; host: string; port: number }>> {
    return get('/sidecar/status')
  },
  stopSidecar(): Promise<ApiResult<{ state: string; message: string }>> {
    return post('/sidecar/stop')
  },
  benchmarkModel(request: BenchmarkRequest): Promise<ApiResult<BenchmarkResponse>> {
    return post<BenchmarkResponse>('/models/benchmark', request)
  },
  getRuntimeSettings(): Promise<ApiResult<RuntimeSettingsResponse>> {
    return get<RuntimeSettingsResponse>('/runtime/settings')
  },
  updateRuntimeSettings(request: RuntimeSettingsRequest): Promise<ApiResult<RuntimeSettingsResponse>> {
    return put<RuntimeSettingsResponse>('/runtime/settings', request)
  },
  resetRuntimeSettings(): Promise<ApiResult<RuntimeSettingsResponse>> {
    return post<RuntimeSettingsResponse>('/runtime/settings/reset')
  },
  listVoices(): Promise<ApiResult<VoicesResponse>> {
    return get<VoicesResponse>('/tts/voices')
  },
  getTtsCacheSize(): Promise<ApiResult<TtsCacheSizeResponse>> {
    return get<TtsCacheSizeResponse>('/tts/cache/size')
  },
  clearTtsCache(): Promise<ApiResult<TtsCacheClearResponse>> {
    return post<TtsCacheClearResponse>('/tts/cache/clear')
  },
  getBackchannels(): Promise<ApiResult<BackchannelsResponse>> {
    return get<BackchannelsResponse>('/tts/backchannels')
  },
  vadHealth(): Promise<ApiResult<VadHealthResponse>> {
    return get<VadHealthResponse>('/vad/health')
  },
  recordOnboardingOutcome(outcome: string): Promise<ApiResult<undefined>> {
    return post<undefined>('/setup/outcome', { outcome })
  },
  getSetupStatus(): Promise<ApiResult<import('../setup/SetupStatus').SetupStatusResponse>> {
    return get<import('../setup/SetupStatus').SetupStatusResponse>('/setup/status')
  },
  startSetupInstall(registryId: string): Promise<ApiResult<SetupInstallJob>> {
    return post<SetupInstallJob>('/setup/install', { registry_id: registryId })
  },
  getSetupInstallStatus(jobId: number): Promise<ApiResult<SetupInstallJob>> {
    return get<SetupInstallJob>(`/setup/install/${jobId}`)
  },
  cancelSetupInstall(jobId: number): Promise<ApiResult<undefined>> {
    return del(`/setup/install/${jobId}`)
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
    listPacks(): Promise<ApiResult<WorkbenchPack[]>> {
      return get<WorkbenchPack[]>('/workbench/packs')
    },
    listFiles(kind: PackKind, slug: string): Promise<ApiResult<{ tree: FileNode[] }>> {
      return get<{ tree: FileNode[] }>(`/workbench/packs/${kind}/${slug}/files`)
    },
    readFile(kind: PackKind, slug: string, filePath: string): Promise<ApiResult<{ content: string; editable: boolean }>> {
      return get<{ content: string; editable: boolean }>(
        `/workbench/packs/${kind}/${slug}/file?path=${encodeURIComponent(filePath)}`,
      )
    },
    writeFile(kind: PackKind, slug: string, filePath: string, content: string): Promise<ApiResult<WriteFileResult>> {
      return put<WriteFileResult>(
        `/workbench/packs/${kind}/${slug}/file?path=${encodeURIComponent(filePath)}`,
        { content },
      )
    },
    validate(kind: PackKind, slug: string): Promise<ApiResult<WorkbenchValidation>> {
      return get<WorkbenchValidation>(`/workbench/packs/${kind}/${slug}/validate`)
    },
    copyToLocal(kind: PackKind, slug: string): Promise<ApiResult<WorkbenchPack>> {
      return post<WorkbenchPack>(`/workbench/packs/${kind}/${slug}/copy-to-local`)
    },
    startTestSession(kind: PackKind, slug: string): Promise<ApiResult<WorkbenchTestSession>> {
      return post<WorkbenchTestSession>(`/workbench/packs/${kind}/${slug}/test-session`)
    },
    async importPack(
      file: File,
      conflict?: 'rename' | 'overwrite',
    ): Promise<ApiResult<WorkbenchImportResult | WorkbenchImportValidationError>> {
      const url = conflict
        ? `${BASE}/workbench/packs/import?conflict=${conflict}`
        : `${BASE}/workbench/packs/import`
      try {
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
          let data: { valid?: false; errors?: WorkbenchValidationIssue[]; warnings?: WorkbenchValidationIssue[]; message?: string } | null = null
          try { data = JSON.parse(await res.text()) } catch { /* ignore */ }
          if (data && Array.isArray(data.errors)) {
            return { ok: true, data: { kind: 'validation', valid: false, errors: data.errors, warnings: data.warnings ?? [] } }
          }
          return {
            ok: false,
            error: {
              kind: 'http-error',
              message: data?.message ?? 'Import failed: the uploaded file could not be processed',
              status: 422,
            },
          }
        }
        return handleResponse<WorkbenchImportResult>(res)
      } catch (err) {
        return { ok: false, error: { kind: 'network', message: err instanceof Error ? err.message : 'Network error' } }
      }
    },
    async exportPack(kind: PackKind, slug: string): Promise<ApiResult<{ blob: Blob; filename: string }>> {
      try {
        const res = await fetch(`${BASE}/workbench/packs/${kind}/${slug}/export`)
        if (res.status === 422) {
          // Validation preflight failed — surface the first error message.
          let data: { errors: WorkbenchValidationIssue[] } | null = null
          try { data = JSON.parse(await res.text()) } catch { /* ignore */ }
          const first = data?.errors?.[0]
          return {
            ok: false,
            error: {
              kind: 'http-error',
              message: first
                ? `Export blocked: ${first.message} (${first.rule_id})`
                : 'Pack validation failed before export',
              status: 422,
            },
          }
        }
        if (!res.ok) {
          return { ok: false, error: await errorFromResponse(res) }
        }
        const blob = await res.blob()
        const disposition = res.headers.get('Content-Disposition') ?? ''
        const match = /filename="([^"]+)"/.exec(disposition)
        const filename = match?.[1] ?? `${slug}.zip`
        return { ok: true, data: { blob, filename } }
      } catch (err) {
        return { ok: false, error: { kind: 'network', message: err instanceof Error ? err.message : 'Network error' } }
      }
    },
  },

  workshop: {
    /**
     * Sync the given Steam Workshop subscribed items through the validation
     * pipeline. Valid packs are imported into the pack index; invalid packs are
     * quarantined with a readable reason and never crash the library.
     */
    sync(items: Array<{ item_id: string; install_path: string; needs_update: boolean; updated_at: number }>): Promise<ApiResult<{
      results: Array<{ item_id: string; pack_id: string | null; status: string; reason?: string }>
      imported: number
      updated: number
      unchanged: number
      quarantined: number
      skipped: number
    }>> {
      return post('/workshop/sync', { items })
    },

    /** List all successfully synced Workshop items with their metadata. */
    listItems(): Promise<ApiResult<{ items: Array<{ item_id: string; pack_id: string; author_name: string; install_path: string; workshop_updated_at: number; synced_at: number }> }>> {
      return get('/workshop/items')
    },

    /** List Workshop items that were quarantined due to validation failures. */
    listQuarantine(): Promise<ApiResult<{ items: Array<{ item_id: string; install_path: string; reason: string; quarantined_at: number }> }>> {
      return get('/workshop/quarantine')
    },

    /**
     * Remove a Workshop pack from the local index after unsubscribing via Steam.
     * Returns whether the pack was removed (false when active sessions exist).
     */
    async remove(packId: string): Promise<ApiResult<{ removed: boolean; has_active_sessions: boolean; message: string }>> {
      try {
        const res = await fetch(`${BASE}/workshop/${encodeURIComponent(packId)}`, { method: 'DELETE' })
        return handleResponse<{ removed: boolean; has_active_sessions: boolean; message: string }>(res)
      } catch (err) {
        return { ok: false, error: { kind: 'network', message: err instanceof Error ? err.message : 'Network error' } }
      }
    },
  },
}
