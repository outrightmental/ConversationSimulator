// SPDX-License-Identifier: Apache-2.0
import type { FastifyInstance } from 'fastify';
import type {
  LogbookProfile,
  LogbookExport,
  SessionScoreRecord,
  DimensionScore,
  PersonalRecord,
  ScenarioDifficulty,
} from '@convsim/shared';
import { getDb, WORKBENCH_TEST_SCENARIO_ID } from '../db.js';

interface SessionRow {
  session_id: string;
  scenario_id: string;
  ending_type: string | null;
  created_at: string;
  ended_at: string | null;
  setup_json: string;
  turn_count: number;
}

interface DebriefEventRow {
  session_id: string;
  payload_json: string;
  created_at: string;
}

// Returns YYYY-MM-DD from an ISO timestamp, using the timestamp as-is (UTC).
function toDateStr(iso: string): string {
  return iso.slice(0, 10);
}

// Recency-weighted average. scores[0] = most recent session score.
function computeRollingScore(scores: number[]): number {
  if (scores.length === 0) return 0;
  const DECAY = 0.85;
  let weightedSum = 0;
  let weightSum = 0;
  for (let i = 0; i < scores.length; i++) {
    const w = Math.pow(DECAY, i);
    weightedSum += scores[i] * w;
    weightSum += w;
  }
  return Math.round((weightedSum / weightSum) * 10) / 10;
}

// Count consecutive calendar days ending on today or yesterday.
function computeStreak(dates: string[]): number {
  if (dates.length === 0) return 0;

  const todayMs = Date.now();
  const todayStr = new Date(todayMs).toISOString().slice(0, 10);
  const yesterdayStr = new Date(todayMs - 86_400_000).toISOString().slice(0, 10);

  const unique = [...new Set(dates)].sort().reverse();
  if (unique[0] !== todayStr && unique[0] !== yesterdayStr) return 0;

  let streak = 1;
  let prev = unique[0];
  for (let i = 1; i < unique.length; i++) {
    const curr = unique[i];
    const prevMs = new Date(prev + 'T00:00:00Z').getTime();
    const currMs = new Date(curr + 'T00:00:00Z').getTime();
    if (Math.round((prevMs - currMs) / 86_400_000) === 1) {
      streak++;
      prev = curr;
    } else {
      break;
    }
  }
  return streak;
}

function buildProfile(db: ReturnType<typeof getDb>): LogbookProfile {
  const sessions = db
    .prepare<[string], SessionRow>(
      `SELECT session_id, scenario_id, ending_type, created_at, ended_at, setup_json, turn_count
       FROM sessions
       WHERE state = 'Ended' AND scenario_id != ?
       ORDER BY COALESCE(ended_at, created_at) DESC`,
    )
    .all(WORKBENCH_TEST_SCENARIO_ID);

  const totalSessions = sessions.length;

  let totalPracticeSeconds = 0;
  for (const s of sessions) {
    if (s.ended_at) {
      const diff = new Date(s.ended_at).getTime() - new Date(s.created_at).getTime();
      if (diff > 0) totalPracticeSeconds += Math.round(diff / 1000);
    }
  }

  const sessionDates = sessions.map((s) => toDateStr(s.ended_at ?? s.created_at));
  const streakDays = computeStreak(sessionDates);
  const lastSessionDate = sessions.length > 0 ? toDateStr(sessions[0].ended_at ?? sessions[0].created_at) : null;

  const debriefRows = db
    .prepare<[string], DebriefEventRow>(
      `SELECT se.session_id, se.payload_json, se.created_at
       FROM session_events se
       INNER JOIN sessions s ON s.session_id = se.session_id
       WHERE se.event_type = 'debrief_generated'
         AND s.scenario_id != ?
       ORDER BY se.event_id DESC`,
    )
    .all(WORKBENCH_TEST_SCENARIO_ID);

  // Index sessions by id for O(1) lookup
  const sessionById = new Map(sessions.map((s) => [s.session_id, s]));

  // dimension_id → scores ordered most-recent-first
  const dimScoresMap = new Map<string, number[]>();
  // (scenario_id|difficulty) → best personal record
  const prMap = new Map<string, { best_score: number; achieved_at: string; scenario_id: string; difficulty: string }>();
  // session_id → overall_score (first debrief per session wins)
  const overallBySession = new Map<string, number>();
  // Sessions already folded in. A session can be debriefed more than once
  // (e.g. the debrief screen's retry re-runs generation from the Ended state),
  // producing multiple debrief_generated events. Only the most recent debrief
  // per session should count — otherwise dimension session counts and the
  // recency-weighted rolling score are inflated by re-debriefs. debriefRows is
  // ordered event_id DESC, so the first row seen for a session is the newest.
  const seenSessions = new Set<string>();

  for (const row of debriefRows) {
    if (seenSessions.has(row.session_id)) continue;

    const payload = JSON.parse(row.payload_json) as {
      scores?: Record<string, number>;
      overall_score?: number;
    };

    const session = sessionById.get(row.session_id);
    if (!session) continue;
    seenSessions.add(row.session_id);

    const setup = JSON.parse(session.setup_json) as { difficulty: string };

    for (const [dimId, score] of Object.entries(payload.scores ?? {})) {
      if (!dimScoresMap.has(dimId)) dimScoresMap.set(dimId, []);
      dimScoresMap.get(dimId)!.push(score);
    }

    if (payload.overall_score !== undefined) {
      const prKey = `${session.scenario_id}|${setup.difficulty}`;
      const existing = prMap.get(prKey);
      if (!existing || payload.overall_score > existing.best_score) {
        prMap.set(prKey, {
          best_score: payload.overall_score,
          achieved_at: session.ended_at ?? session.created_at,
          scenario_id: session.scenario_id,
          difficulty: setup.difficulty,
        });
      }

      if (!overallBySession.has(row.session_id)) {
        overallBySession.set(row.session_id, payload.overall_score);
      }
    }
  }

  const dimensionScores: DimensionScore[] = Array.from(dimScoresMap.entries()).map(
    ([dimension_id, scores]) => ({
      dimension_id,
      rolling_score: computeRollingScore(scores),
      session_count: scores.length,
      // scores is most-recent-first; reverse to chronological for the chart.
      trajectory: [...scores].reverse(),
    }),
  );

  let strongestDimension: string | null = null;
  let weakestDimension: string | null = null;
  if (dimensionScores.length > 0) {
    const sorted = [...dimensionScores].sort((a, b) => b.rolling_score - a.rolling_score);
    strongestDimension = sorted[0].dimension_id;
    weakestDimension = sorted[sorted.length - 1].dimension_id;
  }

  // last_session_delta: last session's overall_score minus penultimate session's
  let lastSessionDelta: number | null = null;
  const scoresInOrder = sessions
    .map((s) => overallBySession.get(s.session_id))
    .filter((s): s is number => s !== undefined);
  if (scoresInOrder.length >= 2) {
    lastSessionDelta = scoresInOrder[0] - scoresInOrder[1];
  }

  const personalRecords: PersonalRecord[] = Array.from(prMap.values()).map((pr) => ({
    scenario_id: pr.scenario_id,
    difficulty: pr.difficulty as ScenarioDifficulty,
    best_score: pr.best_score,
    achieved_at: pr.achieved_at,
  }));

  return {
    total_sessions: totalSessions,
    total_practice_seconds: totalPracticeSeconds,
    streak_days: streakDays,
    last_session_date: lastSessionDate,
    dimension_scores: dimensionScores,
    personal_records: personalRecords,
    strongest_dimension: strongestDimension,
    weakest_dimension: weakestDimension,
    last_session_delta: lastSessionDelta,
  };
}

export async function logbookRoutes(app: FastifyInstance) {
  // GET /api/logbook/profile — aggregated training profile across all sessions
  app.get('/api/logbook/profile', async (): Promise<LogbookProfile> => {
    return buildProfile(getDb());
  });

  // GET /api/logbook/export — full JSON export (profile + per-session scores)
  app.get('/api/logbook/export', async (): Promise<LogbookExport> => {
    const db = getDb();
    const profile = buildProfile(db);

    const sessions = db
      .prepare<[string], SessionRow>(
        `SELECT session_id, scenario_id, ending_type, created_at, ended_at, setup_json, turn_count
         FROM sessions
         WHERE state = 'Ended' AND scenario_id != ?
         ORDER BY COALESCE(ended_at, created_at) DESC`,
      )
      .all(WORKBENCH_TEST_SCENARIO_ID);

    const debriefRows = db
      .prepare<[string], DebriefEventRow>(
        `SELECT se.session_id, se.payload_json
         FROM session_events se
         INNER JOIN sessions s ON s.session_id = se.session_id
         WHERE se.event_type = 'debrief_generated'
           AND s.scenario_id != ?
         ORDER BY se.event_id DESC`,
      )
      .all(WORKBENCH_TEST_SCENARIO_ID);

    const scoresBySession = new Map<string, { overall_score: number | null; scores: Record<string, number> }>();
    for (const row of debriefRows) {
      if (!scoresBySession.has(row.session_id)) {
        const payload = JSON.parse(row.payload_json) as {
          scores?: Record<string, number>;
          overall_score?: number;
        };
        scoresBySession.set(row.session_id, {
          overall_score: payload.overall_score ?? null,
          scores: payload.scores ?? {},
        });
      }
    }

    const sessionScores: SessionScoreRecord[] = sessions.map((s) => {
      const setup = JSON.parse(s.setup_json) as { difficulty: string };
      const debrief = scoresBySession.get(s.session_id);
      return {
        session_id: s.session_id,
        scenario_id: s.scenario_id,
        difficulty: setup.difficulty,
        ended_at: s.ended_at,
        overall_score: debrief?.overall_score ?? null,
        scores: debrief?.scores ?? {},
      };
    });

    return {
      exported_at: new Date().toISOString(),
      profile,
      session_scores: sessionScores,
    };
  });
}
