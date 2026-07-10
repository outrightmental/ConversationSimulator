// SPDX-License-Identifier: Apache-2.0
import type { LogbookProfile } from './logbook.js';
import type { ScenarioInfo, ScenarioDifficulty, LadderPosition } from './scenario.js';

export interface Recommendation {
  scenario_id: string;
  pack_id: string;
  title: string;
  recommended_difficulty: ScenarioDifficulty;
  reason: string;
  ladder_position?: LadderPosition;
}

function suggestedDifficulty(score: number): ScenarioDifficulty {
  if (score < 30) return 'warm';
  if (score < 55) return 'standard';
  if (score < 75) return 'hard';
  return 'adversarial';
}

function isCleared(
  scenarioId: string,
  difficulty: ScenarioDifficulty,
  records: LogbookProfile['personal_records'],
): boolean {
  return records.some(
    (r) => r.scenario_id === scenarioId && r.difficulty === difficulty && r.best_score >= 70,
  );
}

/**
 * Recommend up to 3 next scenarios based on the player's skill profile.
 *
 * Cold-start (null profile or zero sessions): returns intro scenarios, one per
 * pack if possible, with the pack's default difficulty.
 *
 * Active profile: ranks scenarios by how well they target the weakest rubric
 * dimensions and recommends a difficulty tier matched to those scores.
 *
 * Only scenarios in the provided list (installed packs) are ever returned.
 */
export function recommendNext(
  profile: LogbookProfile | null,
  scenarios: ScenarioInfo[],
): Recommendation[] {
  if (!Array.isArray(scenarios) || scenarios.length === 0) return [];

  // Cold start: no profile or no completed sessions.
  if (!profile || profile.total_sessions === 0) {
    const intros = scenarios.filter((s) => s.ladder_position === 'intro');
    const pool = intros.length > 0 ? intros : scenarios;
    const seenPacks = new Set<string>();
    const result: Recommendation[] = [];
    for (const s of pool) {
      if (seenPacks.has(s.pack_id)) continue;
      seenPacks.add(s.pack_id);
      result.push({
        scenario_id: s.scenario_id,
        pack_id: s.pack_id,
        title: s.title,
        recommended_difficulty: s.difficulty?.default ?? 'standard',
        reason: 'A good starting point to build your baseline skills.',
        ladder_position: s.ladder_position,
      });
      if (result.length >= 3) break;
    }
    return result;
  }

  // Active profile: rank by weakest-dimension coverage.
  const sorted = [...profile.dimension_scores].sort((a, b) => a.rolling_score - b.rolling_score);
  const weakest = sorted.slice(0, 3);
  const weakDimIds = new Set(weakest.map((d) => d.dimension_id));
  const avgWeakScore =
    weakest.length > 0
      ? weakest.reduce((sum, d) => sum + d.rolling_score, 0) / weakest.length
      : 50;

  const recommendedDifficulty = suggestedDifficulty(avgWeakScore);

  type Scored = { scenario: ScenarioInfo; points: number; reason: string };
  const scored: Scored[] = [];

  for (const s of scenarios) {
    let points = 0;
    let reason = '';

    const taught = s.taught_dimensions ?? [];
    const tested = s.tested_dimensions ?? [];
    const allDims = [...new Set([...taught, ...tested])];
    const matchingWeak = allDims.filter((d) => weakDimIds.has(d));

    if (matchingWeak.length > 0) {
      points += matchingWeak.length * 3;
      // Use the weakest matching dimension for the reason string.
      const topDim = sorted.find((d) => matchingWeak.includes(d.dimension_id));
      const dimId = topDim?.dimension_id ?? matchingWeak[0];
      const dimScore = profile.dimension_scores.find((d) => d.dimension_id === dimId);
      const scoreLabel = dimScore ? Math.round(dimScore.rolling_score) : '—';
      reason = `Your ${dimId.replace(/_/g, ' ')} score (${scoreLabel}) is your weakest metric; this scenario drills it.`;
    }

    // Ladder-position suitability bonus.
    if (avgWeakScore < 40 && s.ladder_position === 'intro') {
      points += 2;
      if (!reason) reason = 'A foundational exercise to strengthen core skills.';
    } else if (avgWeakScore >= 40 && avgWeakScore < 70 && s.ladder_position === 'practice') {
      points += 2;
      if (!reason) reason = 'Practice-level challenge matched to your current progress.';
    } else if (avgWeakScore >= 70 && s.ladder_position === 'stretch') {
      points += 2;
      if (!reason) reason = 'A stretch challenge to push your skills further.';
    }

    // De-prioritize scenarios already cleared at the recommended difficulty.
    if (isCleared(s.scenario_id, recommendedDifficulty, profile.personal_records)) {
      points -= 10;
    }

    // Every installed scenario remains eligible so the training plan always
    // surfaces up to 3 suggestions. Scenarios that lack ladder/dimension
    // metadata simply score 0 and fill the remaining slots after any that
    // target a weak dimension — they never displace a stronger match, but they
    // keep the recommender useful before pack authors add the optional fields.
    if (!reason) reason = 'Broaden your practice with a different scenario.';

    scored.push({ scenario: s, points, reason });
  }

  scored.sort((a, b) => b.points - a.points);

  return scored.slice(0, 3).map(({ scenario: s, reason }) => ({
    scenario_id: s.scenario_id,
    pack_id: s.pack_id,
    title: s.title,
    recommended_difficulty: recommendedDifficulty,
    reason,
    ladder_position: s.ladder_position,
  }));
}
