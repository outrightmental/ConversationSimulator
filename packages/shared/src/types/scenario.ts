export type ScenarioDifficulty = 'easy' | 'normal' | 'hard';

export interface DifficultyOption {
  npc_patience_modifier: number;
  challenge_frequency: 'low' | 'medium' | 'high';
}

export interface ScenarioDifficultyConfig {
  default: ScenarioDifficulty;
  options: Partial<Record<ScenarioDifficulty, DifficultyOption>>;
}

export interface PlayerRole {
  label: string;
  brief: string;
}

export interface ScenarioDuration {
  max_turns: number;
  soft_time_limit_minutes: number;
}

export interface StateVariable {
  type: 'integer';
  min: number;
  max: number;
  default: number;
  visible?: boolean;
}

export interface ScenarioStateConfig {
  variables: Record<string, StateVariable | number>;
  visible_to_player?: string[];
}

export interface ScenarioInfo {
  scenario_id: string;
  title: string;
  summary: string;
  content_rating: string;
  pack_id: string;
  pack_name: string;
  player_role: PlayerRole;
  difficulty: ScenarioDifficultyConfig;
  supported_languages: string[];
  duration: ScenarioDuration;
  state_meters_permitted: boolean;
  voice_supported: boolean;
  safety_summary: string;
  estimated_length_label: string;
  tags?: string[];
  recommended_model?: string[];
}

export interface PackValidationError {
  rule_id?: string;
  file_path?: string;
  message: string;
}

export interface PackValidationResult {
  pack_id: string;
  valid: boolean;
  errors: PackValidationError[];
}
