// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, afterEach, beforeAll, vi } from 'vitest'
import { encodeWav, recordingForUpload, toWavBlob, WAV_SAMPLE_RATE } from '../lib/wavAudio'

// jsdom's Blob has no arrayBuffer(); every webview the app runs in does.
beforeAll(() => {
  if (typeof Blob.prototype.arrayBuffer !== 'function') {
    Blob.prototype.arrayBuffer = function arrayBuffer(this: Blob): Promise<ArrayBuffer> {
      return new Promise((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = () => resolve(reader.result as ArrayBuffer)
        reader.onerror = () => reject(reader.error)
        reader.readAsArrayBuffer(this)
      })
    }
  }
})

async function bytes(blob: Blob): Promise<DataView> {
  return new DataView(await blob.arrayBuffer())
}

function text(view: DataView, offset: number, length: number): string {
  let out = ''
  for (let i = 0; i < length; i++) out += String.fromCharCode(view.getUint8(offset + i))
  return out
}

/** A stand-in for the webview's decoder: hands back fixed channel data. */
function stubDecoder(channels: number[][], sampleRate = WAV_SAMPLE_RATE) {
  const seen: { channels: number; length: number; sampleRate: number }[] = []
  class FakeOfflineAudioContext {
    constructor(channelCount: number, length: number, rate: number) {
      seen.push({ channels: channelCount, length, sampleRate: rate })
    }
    async decodeAudioData(): Promise<AudioBuffer> {
      return {
        numberOfChannels: channels.length,
        length: channels[0].length,
        sampleRate,
        getChannelData: (index: number) => Float32Array.from(channels[index]),
      } as unknown as AudioBuffer
    }
  }
  vi.stubGlobal('OfflineAudioContext', FakeOfflineAudioContext)
  return seen
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('encodeWav', () => {
  it('writes a 16-bit mono PCM header the speech engine can read', async () => {
    const view = await bytes(encodeWav(Float32Array.from([0, 0.5, -0.5, 1]), 16000))

    expect(text(view, 0, 4)).toBe('RIFF')
    expect(view.getUint32(4, true)).toBe(36 + 8)
    expect(text(view, 8, 4)).toBe('WAVE')
    expect(text(view, 12, 4)).toBe('fmt ')
    expect(view.getUint16(20, true)).toBe(1) // PCM
    expect(view.getUint16(22, true)).toBe(1) // mono
    expect(view.getUint32(24, true)).toBe(16000)
    expect(view.getUint32(28, true)).toBe(32000) // byte rate
    expect(view.getUint16(34, true)).toBe(16) // bits per sample
    expect(text(view, 36, 4)).toBe('data')
    expect(view.getUint32(40, true)).toBe(8)
    expect(view.byteLength).toBe(44 + 8)
  })

  it('scales and clamps samples to 16 bits', async () => {
    const view = await bytes(encodeWav(Float32Array.from([0, 1, -1, 2, -2, 0.5]), 16000))
    const samples = [0, 1, 2, 3, 4, 5].map((i) => view.getInt16(44 + i * 2, true))
    expect(samples).toEqual([0, 32767, -32768, 32767, -32768, 16383])
  })

  it('is typed so the upload is recognised as WAV', () => {
    expect(encodeWav(new Float32Array(1), 16000).type).toBe('audio/wav')
  })
})

describe('toWavBlob', () => {
  it('decodes at 16 kHz and mixes stereo down to mono', async () => {
    const seen = stubDecoder([
      [1, 0, -1, 0.5],
      [0, 0, -1, -0.5],
    ])
    const wav = await toWavBlob(new Blob([new Uint8Array([1, 2, 3])], { type: 'audio/webm' }))
    const view = await bytes(wav)

    // Decoding into a 16 kHz context is what resamples the recording.
    expect(seen).toEqual([{ channels: 1, length: 1, sampleRate: 16000 }])
    expect(view.getUint32(24, true)).toBe(16000)
    const samples = [0, 1, 2, 3].map((i) => view.getInt16(44 + i * 2, true))
    expect(samples).toEqual([16383, 0, -32768, 0])
  })

  it('rejects an empty recording', async () => {
    stubDecoder([[]])
    await expect(toWavBlob(new Blob([], { type: 'audio/webm' }))).rejects.toThrow(/empty/i)
  })

  it('rejects where the webview has no decoder', async () => {
    vi.stubGlobal('OfflineAudioContext', undefined)
    vi.stubGlobal('webkitOfflineAudioContext', undefined)
    await expect(toWavBlob(new Blob([new Uint8Array(4)]))).rejects.toThrow(/decoder/i)
  })
})

describe('recordingForUpload', () => {
  it('converts a browser recording to WAV', async () => {
    stubDecoder([[0.25, -0.25]])
    const upload = await recordingForUpload(new Blob([new Uint8Array(8)], { type: 'audio/webm;codecs=opus' }))
    expect(upload.type).toBe('audio/wav')
    expect(upload.size).toBe(44 + 4)
  })

  it('leaves a recording that is already WAV alone', async () => {
    const seen = stubDecoder([[0]])
    const original = new Blob([new Uint8Array(60)], { type: 'audio/wav' })
    expect(await recordingForUpload(original)).toBe(original)
    expect(seen).toEqual([])
  })

  it('falls back to the recording itself when it cannot be decoded', async () => {
    class Broken {
      async decodeAudioData(): Promise<AudioBuffer> {
        throw new Error('EncodingError')
      }
    }
    vi.stubGlobal('OfflineAudioContext', Broken)
    const original = new Blob([new Uint8Array(8)], { type: 'audio/webm' })
    expect(await recordingForUpload(original)).toBe(original)
  })
})
