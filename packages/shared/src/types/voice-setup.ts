// Guided voice setup (issue #487) — the contract behind /voice-setup.
//
// Mirrors the Pydantic models in
// services/convsim-core/convsim_core/routers/voice_setup.py. The split between
// `assets` (weight files the app downloads and verifies) and `engines` (native
// programs the player installs with one command) is the whole point of the
// flow: only the first kind can be automated, and the UI must not blur them.

import type { SetupInstallStageState } from './models.js';

export type VoiceCapabilityId = 'stt' | 'tts' | 'vad';

/** A weight file the app can download, with everything the confirmation step must disclose. */
export interface VoiceAsset {
  id: string;
  capability: VoiceCapabilityId;
  name: string;
  description: string;
  /** e.g. "English only" / "Multilingual"; empty when not language-specific. */
  language_note: string;
  /** The one-click default for its capability. */
  recommended: boolean;
  /** Currently the file the engine is pointed at. */
  selected: boolean;
  size_bytes: number;
  license: string;
  license_url: string;
  source_url: string;
  sha256: string;
  install_path: string;
  installed: boolean;
}

/** A native program voice needs that the app deliberately does not download. */
export interface VoiceEngine {
  id: string;
  capability: VoiceCapabilityId;
  name: string;
  why_manual: string;
  docs_url: string;
  /** Install command for the player's platform; null when none is listed. */
  command: string | null;
  /** The app can start it once the binary exists (the Kokoro server). */
  startable: boolean;
  installed: boolean;
  found_at: string | null;
}

export interface VoiceCapability {
  id: VoiceCapabilityId;
  label: string;
  description: string;
  ready: boolean;
  required_engine_ids: string[];
  asset_ids: string[];
}

export interface VoiceSetupPlan {
  capabilities: VoiceCapability[];
  assets: VoiceAsset[];
  engines: VoiceEngine[];
  /** Node-style platform string from the server: 'darwin' | 'linux' | 'win32' | … */
  platform: string;
  kokoro_state: string | null;
  onnxruntime_installed: boolean;
  ffmpeg_installed: boolean;
  active_job_id: number | null;
  default_asset_ids: string[];
  /** Bytes the one-click path would transfer now; excludes what is already installed. */
  default_download_bytes: number;
}

export type VoiceInstallJobStatus =
  | 'pending'
  | 'running'
  | 'cancelled'
  | 'complete'
  | 'failed';

export interface VoiceInstallStage {
  /** The asset id this stage downloads. */
  id: string;
  label: string;
  state: SetupInstallStageState;
  bytes_downloaded: number | null;
  bytes_total: number | null;
  error: string | null;
}

export interface VoiceInstallJob {
  id: number;
  status: VoiceInstallJobStatus;
  asset_ids: string[];
  stages: VoiceInstallStage[];
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface StartVoiceEngineResponse {
  engine_id: string;
  state: string;
  started: boolean;
  message: string;
}

/** Overall percentage across a job's stages, or null when nothing is known yet. */
export function computeVoiceInstallPct(job: VoiceInstallJob | null): number | null {
  if (job == null || job.stages.length === 0) return null;
  const total = job.stages.length;
  let done = 0;
  for (const stage of job.stages) {
    if (stage.state === 'complete' || stage.state === 'skipped') {
      done += 1;
    } else if (stage.state === 'running' && stage.bytes_total != null && stage.bytes_total > 0) {
      done += Math.min(1, (stage.bytes_downloaded ?? 0) / stage.bytes_total);
    }
  }
  return Math.round((done / total) * 100);
}

/** Human-readable byte size for download disclosures ("142 MB", "1.2 GB"). */
export function formatDownloadSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${Math.round(bytes / (1024 * 1024))} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}
