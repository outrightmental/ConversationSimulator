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

export type InstallStatus = 'pending' | 'downloading' | 'complete' | 'failed';

export interface InstalledModelInfo {
  id: number;
  registry_id: string | null;
  filename: string;
  file_path: string;
  size_bytes: number | null;
  install_status: InstallStatus;
  progress_bytes: number | null;
  error_message: string | null;
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
