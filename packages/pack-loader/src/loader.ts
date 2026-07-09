// SPDX-License-Identifier: Apache-2.0
import { readdirSync, statSync, lstatSync, existsSync, openSync, readSync, closeSync } from 'node:fs';
import { resolve, join, relative, dirname, normalize, extname } from 'node:path';
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
  ValidationWarning,
} from './types.js';
import { PackLoaderError } from './types.js';

// ---------------------------------------------------------------------------
// Security: executable file detection
// ---------------------------------------------------------------------------

const FORBIDDEN_EXTENSIONS = new Set([
  '.exe', '.bat', '.cmd', '.sh', '.ps1', '.py', '.js', '.mjs', '.cjs',
  '.ts', '.rb', '.pl', '.php', '.jar', '.class', '.so', '.dll', '.dylib',
  '.vbs', '.ws', '.wsf', '.com', '.scr', '.pif', '.msi', '.deb', '.rpm',
  '.pkg', '.app', '.command', '.wasm',
]);

// Magic-byte prefixes that identify executable binary formats regardless of extension.
// Stored as [bytes, description] pairs so the error message names the detected format.
const EXECUTABLE_MAGIC_SIGNATURES: Array<[Uint8Array, string]> = [
  [new Uint8Array([0x7f, 0x45, 0x4c, 0x46]),          'ELF (Linux/Unix executable or shared library)'],
  [new Uint8Array([0xfe, 0xed, 0xfa, 0xce]),            'Mach-O big-endian 32-bit'],
  [new Uint8Array([0xce, 0xfa, 0xed, 0xfe]),            'Mach-O little-endian 32-bit'],
  [new Uint8Array([0xfe, 0xed, 0xfa, 0xcf]),            'Mach-O big-endian 64-bit'],
  [new Uint8Array([0xcf, 0xfa, 0xed, 0xfe]),            'Mach-O little-endian 64-bit'],
  [new Uint8Array([0xca, 0xfe, 0xba, 0xbe]),            'Mach-O universal/fat binary'],
  [new Uint8Array([0x00, 0x61, 0x73, 0x6d]),            'WebAssembly module'],
  [new Uint8Array([0x4d, 0x5a]),                        'Windows PE (executable or DLL)'],
  [new Uint8Array([0x23, 0x21]),                        'shebang (script interpreter directive)'],
];

function readFileHeader(filePath: string): Buffer {
  const buf = Buffer.alloc(8);
  let fd: number | undefined;
  try {
    fd = openSync(filePath, 'r');
    readSync(fd, buf, 0, 8, 0);
  } catch {
    return Buffer.alloc(0);
  } finally {
    if (fd !== undefined) closeSync(fd);
  }
  return buf;
}

function bufferStartsWith(buf: Buffer, prefix: Uint8Array): boolean {
  if (buf.length < prefix.length) return false;
  for (let i = 0; i < prefix.length; i++) {
    if (buf[i] !== prefix[i]) return false;
  }
  return true;
}

/**
 * Recursively scan `packDir` for forbidden files.
 *
 * Rejects:
 * - Symbolic links (can escape the pack root)
 * - Files with executable extensions (see FORBIDDEN_EXTENSIONS)
 * - Files whose content matches known executable magic bytes (disguised binaries)
 *
 * Throws PackLoaderError on the first violation found.  MVP packs are data, not code.
 */
function scanPackForForbiddenContent(packDir: string): void {
  function scan(dir: string): void {
    let entries: string[];
    try {
      entries = readdirSync(dir);
    } catch {
      return;
    }
    for (const name of entries) {
      const fullPath = join(dir, name);
      let st;
      try {
        st = lstatSync(fullPath);
      } catch {
        continue;
      }

      if (st.isSymbolicLink()) {
        const rel = relative(packDir, fullPath).replace(/\\/g, '/');
        throw new PackLoaderError(
          'FORBIDDEN_FILE',
          `Symlinks are not permitted in a pack: '${rel}'. ` +
          'Remove the symlink and include the file content directly.',
          fullPath,
        );
      }

      if (st.isDirectory()) {
        scan(fullPath);
        continue;
      }

      if (!st.isFile()) continue;

      const rel = relative(packDir, fullPath).replace(/\\/g, '/');
      const ext = extname(name).toLowerCase();

      if (FORBIDDEN_EXTENSIONS.has(ext)) {
        throw new PackLoaderError(
          'FORBIDDEN_FILE',
          `Executable or script file not allowed in pack: '${rel}'. ` +
          'MVP packs are data, not code.',
          fullPath,
        );
      }

      const header = readFileHeader(fullPath);
      for (const [magic, fmtName] of EXECUTABLE_MAGIC_SIGNATURES) {
        if (bufferStartsWith(header, magic)) {
          throw new PackLoaderError(
            'FORBIDDEN_BINARY',
            `File '${rel}' contains executable binary content ` +
            `(${fmtName}, detected by magic-byte signature). ` +
            'MVP packs are data, not code — executable content is not permitted ' +
            'even when given a non-executable file extension.',
            fullPath,
          );
        }
      }
    }
  }
  scan(packDir);
}

// ---------------------------------------------------------------------------
// Content analysis: external URLs and prompt-injection risk detection
// ---------------------------------------------------------------------------

// Matches http:// or https:// URLs embedded in plain text.
// External URLs violate the offline-first requirement.
const EXTERNAL_URL_RE = /https?:\/\/[^\s"',;<>)]+/gi;

// Prompt-injection patterns: strings that attempt to override the system
// prompt or re-assign the model's role. Each entry is [regex, label].
const INJECTION_PATTERNS: Array<[RegExp, string]> = [
  // Instruction-override phrasings such as "ignore previous instructions",
  // "ignore all previous instructions", "disregard the above rules", etc.
  // Allow up to three qualifier words (all/the/previous/prior/above/…) between
  // the verb and the target noun so multi-qualifier phrasings are still caught.
  [/(?:ignore|disregard|override|forget)\s+(?:\w+\s+){0,3}(?:instructions?|prompts?|directives?|rules?|context|system\s+prompt)/i, 'instruction-override'],
  [/forget\s+everything\s+(you|i|we)/i, 'forget-directive'],
  [/\{\{[^}]{1,500}\}\}/,                                                               'template-injection'],
  [/\$\{[^}]{1,500}\}/,                                                                 'expression-injection'],
  [/<\s*(system|assistant|im_start)\s*>/i,                                               'role-tag'],
  [/\[INST\]|\[\/INST\]/i,                                                               'llama-instruction-tag'],
  [/###\s*(system|assistant|instruction)\s*:/i,                                          'markdown-role-heading'],
];

function scanTextForExternalUrl(text: string, field: string): ValidationWarning | null {
  EXTERNAL_URL_RE.lastIndex = 0;
  const match = EXTERNAL_URL_RE.exec(text);
  if (!match) return null;
  return {
    code: 'EXTERNAL_URL',
    message:
      `"${field}" contains external URL "${match[0]}". ` +
      'Packs must be offline-first — external URLs in content fields are not loaded at runtime ' +
      'but may mislead players or cause confusion. Remove or replace with a local asset.',
    field,
  };
}

function scanTextForInjection(text: string, field: string): ValidationWarning | null {
  for (const [re, label] of INJECTION_PATTERNS) {
    if (re.test(text)) {
      return {
        code: 'PROMPT_INJECTION_RISK',
        message:
          `"${field}" contains a pattern that resembles prompt injection (${label}). ` +
          'Review this text carefully before publishing — it may interfere with the NPC ' +
          'runtime system prompt and produce unpredictable behaviour.',
        field,
      };
    }
  }
  return null;
}

/**
 * Scan loaded pack content for non-fatal issues: external URLs and
 * prompt-injection-like patterns in text that will be embedded in LLM prompts.
 */
function analyzePackContent(
  scenarios: LoadedScenario[],
  npcs: Map<string, RawNpc>,
  scenes: Map<string, RawScene>,
): ValidationWarning[] {
  const warnings: ValidationWarning[] = [];

  function add(w: ValidationWarning | null): void {
    if (w) warnings.push(w);
  }

  // ── NPCs ──────────────────────────────────────────────────────────────────
  for (const npc of npcs.values()) {
    const id = npc.npc_id;
    for (const [key, text] of Object.entries({
      'public_persona.occupation':    npc.public_persona.occupation,
      'public_persona.speaking_style': npc.public_persona.speaking_style,
      'public_persona.demeanor':       npc.public_persona.demeanor,
    })) {
      const field = `npcs/${id}/${key}`;
      add(scanTextForExternalUrl(text, field));
      add(scanTextForInjection(text, field));
    }

    // Private persona is the highest-risk injection surface.
    const pp = npc.private_persona as Record<string, unknown>;
    for (const [ppKey, ppVal] of Object.entries(pp)) {
      if (Array.isArray(ppVal)) {
        ppVal.forEach((item, i) => {
          if (typeof item === 'string') {
            const field = `npcs/${id}/private_persona/${ppKey}[${i}]`;
            add(scanTextForExternalUrl(item, field));
            add(scanTextForInjection(item, field));
          }
        });
      } else if (typeof ppVal === 'string') {
        const field = `npcs/${id}/private_persona/${ppKey}`;
        add(scanTextForExternalUrl(ppVal, field));
        add(scanTextForInjection(ppVal, field));
      }
    }
  }

  // ── Scenarios ─────────────────────────────────────────────────────────────
  for (const { relPath, data } of scenarios) {
    const prefix = `scenarios/${relPath}`;
    for (const [key, text] of Object.entries({
      'summary':            data.summary,
      'player_role.brief':  data.player_role.brief,
      'opening.npc_says':   data.opening.npc_says,
    })) {
      const field = `${prefix}/${key}`;
      add(scanTextForExternalUrl(text, field));
      add(scanTextForInjection(text, field));
    }
    if (data.goals.player_visible) {
      data.goals.player_visible.forEach((g, i) => {
        const field = `${prefix}/goals/player_visible[${i}]`;
        add(scanTextForExternalUrl(g, field));
        add(scanTextForInjection(g, field));
      });
    }
  }

  // ── Scenes ────────────────────────────────────────────────────────────────
  for (const scene of scenes.values()) {
    const field = `scenes/${scene.scene_id}/description`;
    add(scanTextForExternalUrl(scene.description, field));
    add(scanTextForInjection(scene.description, field));
  }

  return warnings;
}

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

  // ── Security scan ─────────────────────────────────────────────────────────
  // Reject executable files, symlinks, and disguised binaries before any YAML
  // is parsed.  MVP packs are strictly declarative data — no executable content.
  scanPackForForbiddenContent(normalPackDir);

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
        // Portrait paths are pack-root-relative per the NPC schema ("within the pack").
        // resolveRef checks path-traversal; existence is a soft warning (assets may be placeholder).
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
          // Background paths are pack-root-relative per the scene schema ("within the pack assets directory").
          // resolveRef checks path-traversal; existence is a soft warning (assets may be placeholder).
          resolveRef(normalPackDir, normalPackDir, scene.background);
        }
        scenes.set(sceneAbsPath, scene);
      }
    }
  }

  // ── entry_scenarios: path traversal + existence check ─────────────────────
  // Done after discovery so we can verify each ref points to a loaded file.
  const scenarioFileSet = new Set(scenarioFiles);
  for (const entryPath of manifest.entry_scenarios ?? []) {
    const absEntryPath = resolveRef(normalPackDir, normalPackDir, entryPath);
    if (!scenarioFileSet.has(absEntryPath)) {
      throw new PackLoaderError(
        'MISSING_FILE',
        `entry_scenario "${entryPath}" not found in scenarios for pack "${manifest.pack_id}"`,
        absEntryPath,
      );
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

  // ── Asset existence warnings ───────────────────────────────────────────────
  // Portrait and background files are optional cosmetic assets.  Their absence
  // is a warning rather than an error so that packs with placeholder paths can
  // still load and run during development.
  const assetWarnings: ValidationWarning[] = [];

  for (const npc of npcs.values()) {
    if (npc.portrait !== undefined) {
      const portraitAbs = resolveRef(normalPackDir, normalPackDir, npc.portrait);
      if (!existsSync(portraitAbs)) {
        assetWarnings.push({
          code: 'MISSING_ASSET',
          message:
            `NPC "${npc.npc_id}" declares portrait "${npc.portrait}" but the file does not exist. ` +
            'Add the image file or remove the portrait field before publishing.',
          field: `npcs/${npc.npc_id}/portrait`,
        });
      }
    }
  }

  for (const scene of scenes.values()) {
    if (scene.background !== undefined) {
      const bgAbs = resolveRef(normalPackDir, normalPackDir, scene.background);
      if (!existsSync(bgAbs)) {
        assetWarnings.push({
          code: 'MISSING_ASSET',
          message:
            `Scene "${scene.scene_id}" declares background "${scene.background}" but the file does not exist. ` +
            'Add the image file or remove the background field before publishing.',
          field: `scenes/${scene.scene_id}/background`,
        });
      }
    }
  }

  // ── Content analysis: external URLs and injection patterns ─────────────────
  const contentWarnings = analyzePackContent(scenarios, npcs, scenes);

  return {
    manifest,
    packRoot: normalPackDir,
    packRootKind: kind,
    scenarios,
    npcs,
    rubrics,
    scenes,
    safety,
    warnings: [...assetWarnings, ...contentWarnings],
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
    if (!scene) {
      throw new PackLoaderError(
        'MISSING_FILE',
        `Scene not loaded for scenario "${scenarioId}" in pack "${pack.manifest.pack_id}"`,
      );
    }
  }

  return {
    scenarioId,
    packId: pack.manifest.pack_id,
    packRoot: pack.packRoot,
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
 * When the same pack_id appears in multiple roots, the pack with the highest
 * semver version is selected.
 */
export function loadPacksFromRoots(config: PackRootConfig): LoadRootsResult {
  const roots: Array<{ dir: string; kind: PackRootKind }> = [];
  if (config.officialRoot) roots.push({ dir: config.officialRoot, kind: 'official' });
  if (config.communityRoot) roots.push({ dir: config.communityRoot, kind: 'community' });
  if (config.localDevRoot) roots.push({ dir: config.localDevRoot, kind: 'local-dev' });

  const loaded: LoadedPack[] = [];
  const errors: Array<{ dir: string; error: Error }> = [];

  for (const { dir, kind } of roots) {
    let packDirs: string[];
    try {
      packDirs = readdirSync(dir)
        .map((name) => join(dir, name))
        .filter((d) => {
          try {
            return statSync(d).isDirectory();
          } catch {
            return false;
          }
        });
    } catch {
      continue;
    }
    for (const packDir of packDirs) {
      try {
        loaded.push(loadPack(packDir, kind));
      } catch (error) {
        errors.push({ dir: packDir, error: error as Error });
      }
    }
  }

  // Deduplicate: when the same pack_id appears across roots, keep the pack
  // with the highest semver version so the latest compatible release wins.
  const best = new Map<string, LoadedPack>();
  for (const pack of loaded) {
    const existing = best.get(pack.manifest.pack_id);
    if (!existing || compareSemver(pack.manifest.version, existing.manifest.version) > 0) {
      best.set(pack.manifest.pack_id, pack);
    }
  }

  return { packs: [...best.values()], errors };
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

/** Compare two semver strings. Returns positive if a > b, negative if a < b, 0 if equal. */
function compareSemver(a: string, b: string): number {
  const parse = (v: string): [number, number, number] => {
    const parts = v
      .replace(/[^0-9.]/g, '')
      .split('.')
      .map((n) => parseInt(n, 10) || 0);
    return [parts[0] ?? 0, parts[1] ?? 0, parts[2] ?? 0];
  };
  const [aMaj, aMin, aPat] = parse(a);
  const [bMaj, bMin, bPat] = parse(b);
  return aMaj !== bMaj ? aMaj - bMaj : aMin !== bMin ? aMin - bMin : aPat - bPat;
}
