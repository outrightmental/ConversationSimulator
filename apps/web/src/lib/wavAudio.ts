// SPDX-License-Identifier: Apache-2.0
//
// Turn a microphone recording into WAV before it is sent for transcription.
//
// The browser records compressed audio (WebM or Ogg with Opus, MP4 on
// WebKit). The speech engine a voice install provides reads WAV only, and
// the older whisper.cpp path needed ffmpeg on the player's machine to read
// anything else. The webview already has a decoder for whatever it just
// recorded, so the conversion happens here and the player installs nothing.
//
// 16 kHz mono 16-bit is what Whisper works in. Sending exactly that keeps
// the upload small (about 32 KB per second) and leaves the engine nothing to
// resample.

/** Sample rate Whisper models are trained on. */
export const WAV_SAMPLE_RATE = 16000

type OfflineContextCtor = new (channels: number, length: number, sampleRate: number) => OfflineAudioContext

function offlineContextCtor(): OfflineContextCtor | null {
  const scope = globalThis as unknown as {
    OfflineAudioContext?: OfflineContextCtor
    webkitOfflineAudioContext?: OfflineContextCtor
  }
  return scope.OfflineAudioContext ?? scope.webkitOfflineAudioContext ?? null
}

/** Encode mono float samples (-1..1) as a 16-bit PCM WAV file. */
export function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const dataBytes = samples.length * 2
  const buffer = new ArrayBuffer(44 + dataBytes)
  const view = new DataView(buffer)
  const ascii = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i))
  }

  ascii(0, 'RIFF')
  view.setUint32(4, 36 + dataBytes, true)
  ascii(8, 'WAVE')
  ascii(12, 'fmt ')
  view.setUint32(16, 16, true) // fmt chunk size
  view.setUint16(20, 1, true) // PCM
  view.setUint16(22, 1, true) // mono
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true) // byte rate
  view.setUint16(32, 2, true) // block align
  view.setUint16(34, 16, true) // bits per sample
  ascii(36, 'data')
  view.setUint32(40, dataBytes, true)

  let offset = 44
  for (let i = 0; i < samples.length; i++) {
    const clamped = Math.max(-1, Math.min(1, samples[i]))
    view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true)
    offset += 2
  }
  return new Blob([buffer], { type: 'audio/wav' })
}

/** Average an AudioBuffer's channels into one. */
function toMono(audio: AudioBuffer): Float32Array {
  if (audio.numberOfChannels === 1) return audio.getChannelData(0)
  const mono = new Float32Array(audio.length)
  for (let channel = 0; channel < audio.numberOfChannels; channel++) {
    const data = audio.getChannelData(channel)
    for (let i = 0; i < data.length; i++) mono[i] += data[i]
  }
  for (let i = 0; i < mono.length; i++) mono[i] /= audio.numberOfChannels
  return mono
}

/**
 * Decode a recording and re-encode it as 16 kHz mono WAV.
 *
 * Rejects when this webview cannot decode the recording. An offline context
 * is used because decoding into one resamples to its rate, and because it
 * needs no audio device and no user gesture.
 */
export async function toWavBlob(recording: Blob): Promise<Blob> {
  const Ctor = offlineContextCtor()
  if (Ctor == null) throw new Error('This webview has no audio decoder.')
  const context = new Ctor(1, 1, WAV_SAMPLE_RATE)
  const decoded = await context.decodeAudioData(await recording.arrayBuffer())
  if (decoded.length === 0) throw new Error('The recording is empty.')
  return encodeWav(toMono(decoded), decoded.sampleRate)
}

/**
 * The form of a recording to upload: WAV when it can be made, the recording
 * as it is when it cannot. Never rejects. A recording that could not be
 * converted is still worth sending, because a whisper.cpp setup with ffmpeg
 * reads it, and the engine's own refusal is clearer than a silent drop.
 */
export async function recordingForUpload(recording: Blob): Promise<Blob> {
  if (recording.type.includes('wav')) return recording
  try {
    return await toWavBlob(recording)
  } catch {
    return recording
  }
}
