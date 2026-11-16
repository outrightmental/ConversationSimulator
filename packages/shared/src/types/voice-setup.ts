// SPDX-License-Identifier: Apache-2.0
//
// One-click voice install. Mirrors the response models in
// services/convsim-core/convsim_core/routers/voice_setup.py; see
// docs/voice-setup.md.

/** The two things voice gives a player: a way to speak, a way to hear. */
export type VoiceComponentId = 'stt' | 'tts';

/** One file a voice install fetches, as disclosed before the download. */
export interface VoiceDownloadInfo {
  url: string;
  size_bytes: number;
  sha256: string;
}

/** A unit that is installed as a whole: the engine, or one model. */
export interface VoiceAssetStatus {
  id: string;
  label: string;
  installed: boolean;
  download_bytes: number;
  /** SPDX identifier of the asset's own licence. */
  license: string;
  /** Licences of what it bundles, when that differs. */
  license_note: string | null;
  source_name: string;
  source_url: string;
  downloads: VoiceDownloadInfo[];
}

export interface VoiceComponentStatus {
  id: VoiceComponentId;
  label: string;
  description: string;
  /** Usable right now, through this install or a setup the player made. */
  ready: boolean;
  /** The files of the in-app install are on disk. */
  installed: boolean;
  /** What installing this component alone would still download. */
  download_bytes: number;
  /** Languages it handles (primary subtags), or null for any. */
  languages: string[] | null;
  asset_ids: string[];
}

export type VoiceInstallStageState = 'pending' | 'running' | 'complete' | 'skipped' | 'failed';
export type VoiceInstallJobStatus = 'pending' | 'running' | 'complete' | 'failed' | 'cancelled';

/** Why an install failed. NETWORK can be retried as-is; CHECKSUM means a file
 *  arrived but was not the pinned one; DISK is a full or locked drive; ENGINE
 *  means everything downloaded but the engine does not start on this machine. */
export type VoiceInstallErrorCode =
  | 'NETWORK'
  | 'HTTP'
  | 'CHECKSUM'
  | 'DISK'
  | 'ARCHIVE'
  | 'ENGINE'
  | 'UNSUPPORTED'
  | 'UNKNOWN';

export interface VoiceInstallStage {
  /** An asset id, or "check" for the final does-it-run step. */
  id: string;
  label: string;
  state: VoiceInstallStageState;
  /** What a running stage is doing once its bytes are in. */
  detail: 'downloading' | 'unpacking' | null;
  bytes_downloaded: number | null;
  bytes_total: number | null;
  error: string | null;
}

export interface VoiceInstallJob {
  id: number;
  status: VoiceInstallJobStatus;
  components: VoiceComponentId[];
  stages: VoiceInstallStage[];
  error_message: string | null;
  error_code: VoiceInstallErrorCode | null;
  created_at: string;
  updated_at: string;
}

export interface VoiceSetupStatus {
  /** False where no engine build exists for this kind of computer. */
  supported: boolean;
  unsupported_reason: string | null;
  /** Folder the engine and models are installed into. */
  install_dir: string;
  /** What installing every component that is not ready would download. */
  download_bytes: number;
  /** What the in-app install takes on disk now; 0 when nothing is installed.
   *  Absent from an engine older than voice removal. */
  installed_bytes?: number;
  components: VoiceComponentStatus[];
  assets: VoiceAssetStatus[];
  /** The running job, or the most recent one. */
  job: VoiceInstallJob | null;
}

export interface RemoveVoiceResponse {
  freed_bytes: number;
}

export interface StartVoiceInstallRequest {
  /** Empty or omitted: every component that is not ready. */
  components?: VoiceComponentId[];
}
