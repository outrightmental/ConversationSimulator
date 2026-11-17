// Model manager API request and response types shared between the backend and frontend.

export interface ModelRegistryEntry {
  id: string;
  name: string;
  provider: string;
  family: string | null;
  role: string | null;
  format: string | null;
  license_spdx: string | null;
  license_url: string | null;
  source_type: string | null;
  download_url: string | null;
  sha256: string | null;
  size_gb: number | null;
  min_vram_gb: number | null;
  recommended_vram_gb: number | null;
  context_length: number | null;
  registered_at: string;
}

export type InstallStatus =
  | 'pending'
  | 'downloading'
  | 'complete'
  | 'ready'
  | 'failed'
  | 'cancelled'
  | 'checksum_mismatch';

export interface InstalledModelInfo {
  id: number;
  registry_id: string | null;
  filename: string;
  file_path: string;
  size_bytes: number | null;
  install_status: InstallStatus;
  progress_bytes: number | null;
  error_message: string | null;
  verified_sha256: string | null;
  installed_at: string;
}

export interface DetectedOllamaModel {
  id: string;
  name: string;
  size_category: 'small' | 'medium' | 'large' | null;
}

export interface ActiveModelConfig {
  runtime_id: string | null;
  model_id: string | null;
}

export type RuntimeStatus = 'unavailable' | 'starting' | 'ready' | 'degraded' | 'error';

export interface ModelRuntimeHealth {
  runtime_id: string;
  runtime_name: string;
  status: RuntimeStatus;
  model_id: string | null;
  latency_ms: number | null;
  message: string | null;
  checked_at: string;
}

export interface ModelsResponse {
  registry: ModelRegistryEntry[];
  installed: InstalledModelInfo[];
  ollama_models: DetectedOllamaModel[];
  active: ActiveModelConfig;
  runtime_health: ModelRuntimeHealth;
  total: number;
  last_benchmark: BenchmarkResponse | null;
}

export interface UseModelRequest {
  runtime_id: string;
  model_id?: string | null;
}

export interface UseModelResponse {
  runtime_id: string;
  model_id: string | null;
  runtime_name: string;
  status: RuntimeStatus;
  message: string | null;
}

export interface InstallModelRequest {
  registry_id: string;
}

export interface InstallModelResponse {
  install_id: number;
  registry_id: string;
  status: 'pending';
  message: string | null;
}

export interface RegisterGgufRequest {
  path: string;
  display_name?: string | null;
  family_guess?: string | null;
  context_length?: number | null;
}

export interface RegisterGgufResponse {
  profile_id: number;
  file_path: string;
  display_name: string;
  filename: string;
  family_guess: string | null;
  context_length_default: number | null;
  warnings: string[];
  active_runtime_id: string;
  active_model_id: string;
}

export interface BenchmarkRequest {
  model_id?: string | null;
}

export interface BenchmarkResponse {
  model_id: string;
  runtime_id: string;
  tokens_per_sec: number;
  context_length: number | null;
  warnings: string[];
  output_tokens: number;
  benchmarked_at: string;
}

/** Plain-language reply pacing (issue #501). Scales the NPC's word budget and
 *  the runtime's token budget for a turn; read per turn, so no restart.
 *  Ordered fastest-first, which is the order the Settings panel offers them. */
export const REPLY_SPEEDS = ['fast', 'balanced', 'detailed'] as const;

export type ReplySpeed = (typeof REPLY_SPEEDS)[number];

export function isReplySpeed(value: unknown): value is ReplySpeed {
  return typeof value === 'string' && (REPLY_SPEEDS as readonly string[]).includes(value);
}

/** Which engine build answers (issue #531): the processor, the graphics card
 *  through Vulkan, or Auto — the card when the engine lists a discrete one,
 *  else the processor. Ordered as Settings offers them. */
export const ENGINE_VARIANTS = ['auto', 'vulkan', 'cpu'] as const;

export type EngineVariant = (typeof ENGINE_VARIANTS)[number];

export function isEngineVariant(value: unknown): value is EngineVariant {
  return typeof value === 'string' && (ENGINE_VARIANTS as readonly string[]).includes(value);
}

export interface RuntimeSettings {
  context_length: number | null;
  gpu_layers: number | null;
  threads: number | null;
  temperature: number | null;
  top_p: number | null;
  repeat_penalty: number | null;
  /** null means "never chosen"; the backend then applies 'balanced'. */
  reply_speed: ReplySpeed | null;
  /** null means "never chosen"; the backend then applies 'auto'. Optional so
   *  an older core that predates the field still type-checks. */
  engine_variant?: EngineVariant | null;
}

/** Where the graphics-card engine failed (issue #531). */
export type EngineFailureRung = 'probe' | 'load' | 'first_generation' | 'wrong_output' | 'crash';

export interface EngineStatusResponse {
  /** The player's choice. */
  setting: EngineVariant;
  /** The build the managed engine runs now; null when it is not running. */
  running: 'cpu' | 'vulkan' | 'metal' | null;
  /** The builds this install has. */
  available: Array<'cpu' | 'vulkan' | 'metal'>;
  /** The graphics card the last start chose, if any. */
  device: string | null;
  reason: string | null;
  devices: Array<{ backend_id: string; name: string; total_mib: number | null; free_mib: number | null; kind: string }>;
  /** A remembered graphics-card failure; cleared by a driver update or by
   *  "Try the graphics card again". */
  gpu_failure: { rung: EngineFailureRung; detail: string; device: string | null; at: string } | null;
  /** True until the player has seen the one notice about the failure. */
  notice_pending: boolean;
}

export interface RuntimeSettingsResponse {
  settings: RuntimeSettings;
  recommended: RuntimeSettings;
  requires_restart: boolean;
}

export type RuntimeSettingsRequest = Partial<RuntimeSettings>;

export interface RuntimeSettingsFieldError {
  field: string;
  message: string;
}

// ── One-click install pipeline ─────────────────────────────────────────────

export type SetupInstallStageId = 'engine' | 'model' | 'verify' | 'warmup' | 'packs';
export type SetupInstallStageState = 'pending' | 'running' | 'complete' | 'failed' | 'skipped';
export type SetupInstallJobStatus = 'pending' | 'running' | 'cancelled' | 'complete' | 'failed';

export interface SetupInstallStage {
  id: SetupInstallStageId;
  label: string;
  state: SetupInstallStageState;
  bytes_downloaded: number | null;
  bytes_total: number | null;
  error: string | null;
}

/** Machine-readable kind of a failed install, recorded by the engine next to
 *  the human message. NETWORK means the connection was lost or never made and
 *  a retry can help; HTTP means the server answered with an error status;
 *  CHECKSUM means the file arrived but failed its SHA-256 check; UNKNOWN is
 *  anything else (disk, warmup, a bug). */
export type SetupInstallErrorCode = 'NETWORK' | 'HTTP' | 'CHECKSUM' | 'UNKNOWN';

export interface SetupInstallJob {
  id: number;
  status: SetupInstallJobStatus;
  registry_id: string | null;
  stages: SetupInstallStage[];
  error_message: string | null;
  /** Set on every failure the engine records. null on a job that has not
   *  failed and on one that failed before the engine recorded codes; absent
   *  from an engine that predates the field. Without a code, clients fall back
   *  to reading the message. */
  error_code?: SetupInstallErrorCode | null;
  created_at: string;
  updated_at: string;
}

export interface StartInstallRequest {
  registry_id: string;
}
