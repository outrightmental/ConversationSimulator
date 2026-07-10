// SPDX-License-Identifier: Apache-2.0
import type { FastifyInstance } from 'fastify';
import type { ScenarioInfo, ScenarioDifficulty, DifficultyOption } from '@convsim/shared';
import { loadPack, PackIndex } from '@convsim/pack-loader';
import type { LoadedPack, LoadedScenario, PackRootKind } from '@convsim/pack-loader';
import { SCENARIOS } from '../data/scenarios.js';

let _scenariosDbPath: string | null = null;

export function setScenariosDbPath(dbPath: string | null): void {
  _scenariosDbPath = dbPath;
}

function buildDifficultyConfig(
  rawDiff: { default?: string; options?: Record<string, unknown> } | undefined,
): ScenarioInfo['difficulty'] {
  const defaultDiff = (rawDiff?.default ?? 'normal') as ScenarioDifficulty;
  const rawOptions = (rawDiff?.options ?? {}) as Record<string, Record<string, unknown>>;
  const options: Partial<Record<ScenarioDifficulty, DifficultyOption>> = {};

  for (const [key, val] of Object.entries(rawOptions)) {
    if (key === 'easy' || key === 'normal' || key === 'hard') {
      options[key] = {
        npc_patience_modifier: (val['npc_patience_modifier'] as number | undefined) ?? 0,
        challenge_frequency:
          (val['challenge_frequency'] as 'low' | 'medium' | 'high' | undefined) ?? 'medium',
      };
    }
  }

  if (Object.keys(options).length === 0) {
    options['normal'] = { npc_patience_modifier: 0, challenge_frequency: 'medium' };
  }

  return { default: defaultDiff, options };
}

function packScenarioToScenarioInfo(
  pack: LoadedPack,
  scenario: LoadedScenario,
): ScenarioInfo {
  const m = pack.manifest;
  const s = scenario.data;

  const softLimit =
    s.duration.soft_time_limit_minutes ??
    Math.ceil(s.duration.max_turns * 1.2);
  const minMin = Math.max(5, Math.round(softLimit * 0.75));
  const estimatedLengthLabel =
    minMin < softLimit
      ? `${minMin}–${softLimit} minutes`
      : `${softLimit} minutes`;

  return {
    scenario_id: s.scenario_id,
    title: s.title,
    summary: s.summary,
    content_rating: m.content_rating,
    pack_id: m.pack_id,
    pack_name: m.name,
    player_role: { label: s.player_role.label, brief: s.player_role.brief },
    difficulty: buildDifficultyConfig(
      s.difficulty as { default?: string; options?: Record<string, unknown> } | undefined,
    ),
    supported_languages: m.supported_languages ?? ['en'],
    duration: {
      max_turns: s.duration.max_turns,
      soft_time_limit_minutes: softLimit,
    },
    state_meters_permitted: false,
    // Voice is a runtime TTS/STT capability applied to every scenario, not a
    // per-pack content flag (the pack schema has no voice field). Match the
    // built-in scenarios (all voice_supported) so the library's "Voice only"
    // filter and "Voice supported" chip treat imported packs consistently.
    voice_supported: true,
    safety_summary: `${m.content_rating} rated. Content cap: ${pack.safety.content_rating_cap}.`,
    estimated_length_label: estimatedLengthLabel,
    tags: m.tags ?? [],
    recommended_model: m.requirements?.recommended_llm ?? [],
  };
}

function loadScenariosFromPackIndex(dbPath: string, skipIds: Set<string>): ScenarioInfo[] {
  const index = PackIndex.open(dbPath);
  const results: ScenarioInfo[] = [];
  try {
    const packs = index.listPacks();
    for (const packEntry of packs) {
      try {
        const pack = loadPack(packEntry.pack_root, packEntry.pack_root_kind as PackRootKind);
        for (const scenario of pack.scenarios) {
          if (!skipIds.has(scenario.data.scenario_id)) {
            results.push(packScenarioToScenarioInfo(pack, scenario));
          }
        }
      } catch {
        // Skip packs that fail to load (corrupt, deleted, etc.)
      }
    }
  } finally {
    index.close();
  }
  return results;
}

export async function scenarioRoutes(app: FastifyInstance) {
  app.get('/api/scenarios', async (): Promise<ScenarioInfo[]> => {
    const staticScenarios = Object.values(SCENARIOS);

    if (!_scenariosDbPath) {
      return staticScenarios;
    }

    try {
      const staticIds = new Set(staticScenarios.map((s) => s.scenario_id));
      const dynamicScenarios = loadScenariosFromPackIndex(_scenariosDbPath, staticIds);
      return [...staticScenarios, ...dynamicScenarios];
    } catch {
      return staticScenarios;
    }
  });

  app.get<{ Params: { scenario_id: string } }>(
    '/api/scenarios/:scenario_id',
    async (req, reply): Promise<ScenarioInfo> => {
      const { scenario_id } = req.params;

      const staticScenario = SCENARIOS[scenario_id];
      if (staticScenario) return staticScenario;

      if (_scenariosDbPath) {
        try {
          const allDynamic = loadScenariosFromPackIndex(
            _scenariosDbPath,
            new Set(Object.keys(SCENARIOS)),
          );
          const found = allDynamic.find((s) => s.scenario_id === scenario_id);
          if (found) return found;
        } catch {
          // fall through to 404
        }
      }

      reply.status(404);
      throw new Error(`Scenario '${scenario_id}' not found`);
    },
  );
}
