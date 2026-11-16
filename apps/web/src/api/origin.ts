// SPDX-License-Identifier: Apache-2.0
//
// Where the core service is, as seen from this web view.
//
// In a packaged Tauri build the web UI is served from tauri://localhost
// (macOS/Linux) or https://tauri.localhost (Windows), and there is no Vite
// dev-server proxy, so API traffic goes directly to the core on its fixed
// port. In dev mode (tauri dev, or a browser), Vite proxies /api and /ws, so
// relative paths work.
//
// Kept apart from api/client.ts so that anything built from a URL rather than
// fetched through the client (an <audio> source, for one) can use the same
// origin, and so tests that replace the client still get real URLs.

export const IS_TAURI_PRODUCTION: boolean =
  typeof window !== 'undefined' &&
  '__TAURI__' in window &&
  (window.location.protocol === 'tauri:' ||
    window.location.hostname === 'tauri.localhost')

export const CORE_ORIGIN = 'http://127.0.0.1:7355'

/** The API's base path: absolute in a packaged build, proxied otherwise. */
export function apiBaseFor(packaged: boolean): string {
  return packaged ? `${CORE_ORIGIN}/api` : '/api'
}

export const API_BASE = apiBaseFor(IS_TAURI_PRODUCTION)

/**
 * URL a cached TTS sentence plays from, given the path the core reports for
 * it (an absolute file path on the player's machine, either slash style).
 *
 * It must carry the core's origin. A bare `/api/tts/audio/…` resolves against
 * the web view's own origin in a packaged build, where nothing serves `/api`,
 * and the character stays silent (issue #533).
 */
export function ttsAudioUrl(cachePath: string, base: string = API_BASE): string | null {
  const filename = cachePath.replace(/\\/g, '/').split('/').pop()
  return filename ? `${base}/tts/audio/${filename}` : null
}

/**
 * URL one sentence of a reply is spoken from, given the `audio_path` its
 * `tts_audio_chunk` event carries (a path under `/api`, for example
 * `/sessions/<id>/speech/3/0`).
 *
 * The reply's text arrives before its audio exists; a request to this URL
 * waits until that sentence has been synthesised and then answers with it, so
 * an <audio> element pointed here starts the moment the sentence is ready.
 */
export function speechAudioUrl(audioPath: string, base: string = API_BASE): string | null {
  if (!audioPath.startsWith('/')) return null
  return `${base}${audioPath}`
}
