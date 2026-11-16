// SPDX-License-Identifier: Apache-2.0
//
// Voice install fixtures shared by the card, hook and brief tests. The sizes
// are the real catalog's, so the copy the tests assert is the copy a player
// reads.
import type { VoiceInstallJob, VoiceSetupStatus } from '@convsim/shared'

export const ENGINE = {
  id: 'engine',
  label: 'Speech engine',
  installed: false,
  download_bytes: 24_805_859,
  license: 'Apache-2.0',
  license_note: 'Includes ONNX Runtime (MIT) and eSpeak NG (GPL-3.0-or-later).',
  source_name: 'sherpa-onnx',
  source_url: 'https://github.com/k2-fsa/sherpa-onnx/releases/tag/v1.13.8',
  downloads: [{ url: 'https://example.test/engine.tar.bz2', size_bytes: 24_805_859, sha256: 'a'.repeat(64) }],
}
export const WHISPER = {
  id: 'whisper-base',
  label: 'Listening model (Whisper base)',
  installed: false,
  download_bytes: 160_609_290,
  license: 'MIT',
  license_note: null,
  source_name: 'OpenAI Whisper, converted for sherpa-onnx',
  source_url: 'https://huggingface.co/csukuangfj/sherpa-onnx-whisper-base',
  downloads: [{ url: 'https://example.test/enc', size_bytes: 160_609_290, sha256: 'b'.repeat(64) }],
}
export const KOKORO = {
  id: 'kokoro-v1',
  label: 'Voices (Kokoro v1.0)',
  installed: false,
  download_bytes: 373_349_093,
  license: 'Apache-2.0',
  license_note: 'Pronunciation data from eSpeak NG (GPL-3.0-or-later).',
  source_name: 'Kokoro-82M, converted for sherpa-onnx',
  source_url: 'https://huggingface.co/csukuangfj/kokoro-multi-lang-v1_0',
  downloads: [{ url: 'https://example.test/kokoro', size_bytes: 373_349_093, sha256: 'c'.repeat(64) }],
}

export function voicePlan(overrides: Partial<VoiceSetupStatus> = {}): VoiceSetupStatus {
  return {
    supported: true,
    unsupported_reason: null,
    install_dir: 'C:\\Users\\player\\AppData\\Local\\com.outrightmental.convsim\\models\\voice',
    download_bytes: 558_764_242,
    components: [
      {
        id: 'stt', label: 'Voice input', description: 'Speak your turns instead of typing them.',
        ready: false, installed: false, download_bytes: 185_415_149, languages: null,
        asset_ids: ['engine', 'whisper-base'],
      },
      {
        id: 'tts', label: 'Character voice', description: 'Hear the other person\u2019s replies out loud.',
        ready: false, installed: false, download_bytes: 398_154_952,
        languages: ['en', 'es', 'fr', 'it', 'pt', 'hi'], asset_ids: ['engine', 'kokoro-v1'],
      },
    ],
    assets: [ENGINE, WHISPER, KOKORO],
    job: null,
    ...overrides,
  }
}

export function readyPlan(): VoiceSetupStatus {
  const plan = voicePlan({ download_bytes: 0 })
  return {
    ...plan,
    components: plan.components.map((c) => ({ ...c, ready: true, installed: true, download_bytes: 0 })),
    assets: plan.assets.map((a) => ({ ...a, installed: true })),
  }
}

export function voiceJob(overrides: Partial<VoiceInstallJob> = {}): VoiceInstallJob {
  return {
    id: 1,
    status: 'running',
    components: ['stt', 'tts'],
    stages: [
      { id: 'engine', label: 'Getting the speech engine', state: 'complete', detail: null, bytes_downloaded: 24_805_859, bytes_total: 24_805_859, error: null },
      { id: 'whisper-base', label: 'Downloading the listening model', state: 'running', detail: 'downloading', bytes_downloaded: 80_304_645, bytes_total: 160_609_290, error: null },
      { id: 'kokoro-v1', label: 'Downloading the voices', state: 'pending', detail: null, bytes_downloaded: null, bytes_total: null, error: null },
      { id: 'check', label: 'Checking that it works', state: 'pending', detail: null, bytes_downloaded: null, bytes_total: null, error: null },
    ],
    error_message: null,
    error_code: null,
    created_at: '2026-11-16T00:00:00Z',
    updated_at: '2026-11-16T00:00:05Z',
    ...overrides,
  }
}
