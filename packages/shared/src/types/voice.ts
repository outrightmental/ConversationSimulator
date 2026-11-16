export interface VoiceInfo {
  voice_id: string;
  display_name: string;
  engine: string;
  gender: 'male' | 'female';
  locale: string;
}

export interface VoicesResponse {
  voices: VoiceInfo[];
}

export interface TtsCacheSizeResponse {
  files: number;
  size_bytes: number;
}

export interface TtsCacheClearResponse {
  deleted_files: number;
}

/**
 * Payload of a `tts_audio_chunk` event on the session start and turn
 * responses: one sentence of the reply, to be spoken.
 *
 * The response carries the reply's words before its audio exists (issue
 * #533), so a sentence arrives `pending`, with the address it will be spoken
 * from. A request to that address waits until the sentence has been
 * synthesised and then answers with the audio (404 when synthesis failed).
 * The session's own record of the event is rewritten at that point with
 * `cache_path` or `error`.
 */
export interface TtsAudioChunkPayload {
  /** Zero-based position of this sentence within the reply. */
  chunk_index: number;
  /** Number of sentences in the reply. */
  total_chunks: number;
  /** The sentence. Always present; it is what is shown if there is no audio. */
  text: string;
  /** Voice it is spoken in. */
  voice_id: string;
  /**
   * Where the sentence is spoken from, as a path under `/api`, for example
   * `/sessions/<id>/speech/3/0`. Absent from an engine that still synthesises
   * before answering; such an engine sends `cache_path` instead.
   */
  audio_path?: string;
  /** True while the sentence has not been synthesised yet. */
  pending?: boolean;
  /** Path of the cached WAV on this machine once synthesised, else null. */
  cache_path: string | null;
  /** Why there is no audio, once synthesis has failed; else null. */
  error: string | null;
  /**
   * On the first sentence only: how long the character should seem to think
   * before speaking, in ms. A target, not an addition: the client takes off
   * what the player has already waited for the reply.
   */
  thinking_pause_ms?: number;
}

export interface BackchannelInfo {
  text: string;
  cache_path: string;
}

export interface BackchannelsResponse {
  backchannels: BackchannelInfo[];
}
