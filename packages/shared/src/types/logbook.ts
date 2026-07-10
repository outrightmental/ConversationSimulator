// SPDX-License-Identifier: Apache-2.0
import type { ScenarioDifficulty } from './scenario.js';

export interface DimensionScore {
  dimension_id: string;
  rolling_score: number;
  session_count: number;
}

export interface PersonalRecord {
  scenario_id: string;
  difficulty: ScenarioDifficulty;
  best_score: number;
  achieved_at: string;
}

export interface LogbookProfile {
  total_sessions: number;
  total_practice_seconds: number;
  streak_days: number;
  last_session_date: string | null;
  dimension_scores: DimensionScore[];
  personal_records: PersonalRecord[];
  strongest_dimension: string | null;
  weakest_dimension: string | null;
  last_session_delta: number | null;
}

export interface SessionScoreRecord {
  session_id: string;
  scenario_id: string;
  difficulty: string;
  ended_at: string | null;
  overall_score: number | null;
  scores: Record<string, number>;
}

export interface LogbookExport {
  exported_at: string;
  profile: LogbookProfile;
  session_scores: SessionScoreRecord[];
}
