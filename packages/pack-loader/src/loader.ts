// SPDX-License-Identifier: Apache-2.0
import { readdirSync, statSync } from 'node:fs';
import { resolve, join, relative, dirname, normalize } from 'node:path';
import { resolveRef, readPackFile } from './resolver.js';
import { parseAndValidate } from './validator.js';
import type {
  LoadedPack,
  LoadedScenario,
  PackRootKind,
  RawManifest,
  RawNpc,
  RawRubric,
  RawSafety,
  RawScene,
  RawScenario,
  ResolvedBundle,
} from './types.js';
import { PackLoaderError } from './types.js';

// ---------------------------------------------------------------------------
// Single-pack loader
// ---------------------------------------------------------------------------

/**
 * Load and validate a single pack from `packDir`.
 *
 * - Validates manifest.yaml and all referenced YAML files against their
 *   JSON schemas (schema_version 0.1).
 * - Resolves all relative refs (npc, rubric, scene, safety) and rejects any
 *   ref that would escape the pack root (path traversal).
 * - Rejects packs with duplicate scenario_id or npc_id values.
 * - Does not execute any code from pack files.
 */
export function loadPack(packDir: string, kind: PackRootKind = 'local-dev'): LoadedPack {
  const normalPackDir = normalize(resolve(packDir));

  // ── Manifest ──────────────────────────────────────────────────────────────
  const manifestPath = resolve(normalPackDir, 'manifest.yaml');
  const manifest = parseAndValidate<RawManifest>(
    readPackFile(manifestPath),
    'pack',
    manifestPath,
  );

  // ── Safety policy ─────────────────────────────────────────────────────────
  const safetyPath = resolveRef(normalPackDir, normalPackDir, manifest.safety.policy);
  const safety = parseAndValidate<RawSafety>(readPackFile(safetyPath), 'safety', safetyPath);

  // ── Scenarios ─────────────────────────────────────────────────────────────
  const scenariosDir = resolve(normalPackDir, 'scenarios');
  const scenarioFiles = discoverYamlFiles(scenariosDir);

  const scenarioIds = new Set<string>();
  const scenarios: LoadedScenario[] = [];
  const npcs = new Map<string, RawNpc>();
  const rubrics = new Map<string, RawRubric>();
  const scenes = new Map<string, RawScene>();

  for (const absPath of scenarioFiles) {
    const data = parseAndValidate<RawScenario>(readPackFile(absPath), 'scenario', absPath);

    if (scenarioIds.has(data.scenario_id)) {
      throw new PackLoaderError(
        'DUPLICATE_ID',
        `Duplicate scenario_id "${data.scenario_id}" found in pack "${manifest.pack_id}"`,
        absPath,
      );
    }
    scenarioIds.add(data.scenario_id);

    const scenarioDir = dirname(absPath);
    const relPath = relative(normalPackDir, absPath).replace(/\\/g, '/');
    scenarios.push({ relPath, data });

    // Resolve NPC ref
    const npcAbsPath = resolveRef(scenarioDir, normalPackDir, data.npc.ref);
    if (!npcs.has(npcAbsPath)) {
      const npc = parseAndValidate<RawNpc>(readPackFile(npcAbsPath), 'npc', npcAbsPath);
      if (npc.portrait !== undefined) {
        resolveRef(normalPackDir, normalPackDir, npc.portrait);
      }
      npcs.set(npcAbsPath, npc);
    }

    // Resolve rubric ref
    const rubricAbsPath = resolveRef(scenarioDir, normalPackDir, data.rubric.ref);
    if (!rubrics.has(rubricAbsPath)) {
      const rubric = parseAndValidate<RawRubric>(
        readPackFile(rubricAbsPath),
        'rubric',
        rubricAbsPath,
      );
      rubrics.set(rubricAbsPath, rubric);
    }

    // Resolve optional scene ref
    if (data.scene?.ref) {
      const sceneAbsPath = resolveRef(scenarioDir, normalPackDir, data.scene.ref);
      if (!scenes.has(sceneAbsPath)) {
        const scene = parseAndValidate<RawScene>(readPackFile(sceneAbsPath), 'scene', sceneAbsPath);
        if (scene.background !== undefined) {
          resolveRef(normalPackDir, normalPackDir, scene.background);
        }
        scenes.set(sceneAbsPath, scene);
      }
    }
  }

  // Duplicate NPC id check across all resolved NPCs
  const npcIds = new Set<string>();
  for (const npc of npcs.values()) {
    if (npcIds.has(npc.npc_id)) {
      throw new PackLoaderError(
        'DUPLICATE_ID',
        `Duplicate npc_id "${npc.npc_id}" in pack "${manifest.pack_id}"`,
      );
    }
    npcIds.add(npc.npc_id);
  }

  return {
    manifest,
    packRoot: normalPackDir,
    packRootKind: kind,
    scenarios,
    npcs,
    rubrics,
    scenes,
    safety,
  };
}

// ---------------------------------------------------------------------------
// Bundle resolver
// ---------------------------------------------------------------------------

/**
 * Return a fully resolved scenario bundle — scenario, NPC, rubric, scene,
 * and safety policy — ready for the conversation runtime.
 */
export function resolveBundle(pack: LoadedPack, scenarioId: string): ResolvedBundle {
  const loaded = pack.scenarios.find((s) => s.data.scenario_id === scenarioId);
  if (!loaded) {
    throw new PackLoaderError(
      'MISSING_FILE',
      `Scenario "${scenarioId}" not found in pack "${pack.manifest.pack_id}"`,
    );
  }

  const scenario = loaded.data;
  const scenarioDir = dirname(resolve(pack.packRoot, loaded.relPath));

  const npcPath = resolveRef(scenarioDir, pack.packRoot, scenario.npc.ref);
  const npc = pack.npcs.get(npcPath);
  if (!npc) {
    throw new PackLoaderError(
      'MISSING_FILE',
      `NPC not loaded for scenario "${scenarioId}" in pack "${pack.manifest.pack_id}"`,
    );
  }

  const rubricPath = resolveRef(scenarioDir, pack.packRoot, scenario.rubric.ref);
  const rubric = pack.rubrics.get(rubricPath);
  if (!rubric) {
    throw new PackLoaderError(
      'MISSING_FILE',
      `Rubric not loaded for scenario "${scenarioId}" in pack "${pack.manifest.pack_id}"`,
    );
  }

  let scene: RawScene | null = null;
  if (scenario.scene?.ref) {
    const scenePath = resolveRef(scenarioDir, pack.packRoot, scenario.scene.ref);
    scene = pack.scenes.get(scenePath) ?? null;
  }

  return {
    scenarioId,
    packId: pack.manifest.pack_id,
    scenario,
    npc,
    rubric,
    scene,
    safety: pack.safety,
  };
}

// ---------------------------------------------------------------------------
// Multi-root loader
// ---------------------------------------------------------------------------

export interface PackRootConfig {
  officialRoot?: string;
  communityRoot?: string;
  localDevRoot?: string;
}

export interface LoadRootsResult {
  packs: LoadedPack[];
  errors: Array<{ dir: string; error: Error }>;
}

/**
 * Scan the configured pack roots and load every pack directory found.
 * Packs that fail validation are collected in `errors` and skipped.
 */
export function loadPacksFromRoots(config: PackRootConfig): LoadRootsResult {
  const roots: Array<{ dir: string; kind: PackRootKind }> = [];
  if (config.officialRoot) roots.push({ dir: config.officialRoot, kind: 'official' });
  if (config.communityRoot) roots.push({ dir: config.communityRoot, kind: 'community' });
  if (config.localDevRoot) roots.push({ dir: config.localDevRoot, kind: 'local-dev' });

  const packs: LoadedPack[] = [];
  const errors: Array<{ dir: string; error: Error }> = [];

  for (const { dir, kind } of roots) {
    let packDirs: string[];
    try {
      packDirs = readdirSync(dir)
        .map((name) => join(dir, name))
        .filter((d) => statSync(d).isDirectory());
    } catch {
      continue;
    }
    for (const packDir of packDirs) {
      try {
        packs.push(loadPack(packDir, kind));
      } catch (error) {
        errors.push({ dir: packDir, error: error as Error });
      }
    }
  }

  return { packs, errors };
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function discoverYamlFiles(dir: string): string[] {
  try {
    return readdirSync(dir)
      .filter((f) => f.endsWith('.yaml') || f.endsWith('.yml'))
      .map((f) => resolve(dir, f));
  } catch {
    return [];
  }
}
