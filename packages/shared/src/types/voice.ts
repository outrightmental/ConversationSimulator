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

export interface BackchannelInfo {
  text: string;
  cache_path: string;
}

export interface BackchannelsResponse {
  backchannels: BackchannelInfo[];
}
