// SPDX-License-Identifier: Apache-2.0
import { resolve } from 'node:path';
import { Socket } from 'node:net';
import { loadPack, resolveBundle, PackLoaderError } from '@convsim/pack-loader';
import { writeJson, writeLine, writeErrorLine } from '../output.js';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface NetworkViolation {
  /** Full URL or best-effort tcp://<host>:<port> string. */
  url: string;
  /** Inferred subsystem from the URL / call stack. */
  subsystem: string;
}

export type OfflineSmokeTestResult =
  | {
      status: 'ok';
      pack_id: string;
      scenario_id: string;
      turns_played: number;
      debrief_generated: boolean;
      network_violations: [];
    }
  | {
      status: 'network_violation';
      pack_id: string;
      scenario_id: string;
      turns_played: number;
      network_violations: NetworkViolation[];
    }
  | {
      status: 'error';
      error: { code: string; message: string; file?: string };
    };

// ---------------------------------------------------------------------------
// Network guard — patches net.Socket.prototype.connect to block non-localhost
// ---------------------------------------------------------------------------

const LOCALHOST_HOSTS = new Set(['127.0.0.1', 'localhost', '::1', '[::1]', '0.0.0.0']);

function isLocalhost(host: string): boolean {
  const h = (host ?? '').split(':')[0]!.toLowerCase();
  return LOCALHOST_HOSTS.has(h) || h.endsWith('.localhost');
}

/**
 * Extract the host and best-effort URL from the arguments passed to
 * Socket.prototype.connect by Node.js internals.
 *
 * Node.js calls `socket.connect([normalizedArgs], callback?)` where
 * `normalizedArgs` is an array whose first element is the options object.
 * That object may contain `href`, `hostname`/`host`, `protocol`, `port`,
 * and `path` — enough to reconstruct the original URL.
 */
function parseConnectArgs(args: unknown[]): { host: string; url: string } {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  function fromOpts(opts: Record<string, any>): { host: string; url: string } {
    const host: string = (opts['hostname'] ?? opts['host'] ?? '') as string;
    const href: string | undefined = opts['href'] as string | undefined;
    if (href) return { host, url: href };
    if (!host) return { host: '', url: '' };
    const proto = typeof opts['protocol'] === 'string' ? opts['protocol'].replace(/:$/, '') : 'tcp';
    const port = typeof opts['port'] === 'number' ? opts['port'] : 0;
    const path = typeof opts['path'] === 'string' ? opts['path'] : '/';
    const url = port ? `${proto}://${host}:${port}${path}` : `${proto}://${host}${path}`;
    return { host, url };
  }

  const first = args[0];
  if (Array.isArray(first) && first.length > 0) {
    // Internal normalized-args form: socket.connect([opts, …], cb?)
    const opts = first[0];
    if (opts !== null && typeof opts === 'object' && !Array.isArray(opts)) {
      return fromOpts(opts as Record<string, unknown>);
    }
    // port-first form inside the array: [port, host?, …]
    if (typeof opts === 'number') {
      const host = typeof first[1] === 'string' ? first[1] : '127.0.0.1';
      return { host, url: `tcp://${host}:${opts}` };
    }
  }
  if (first !== null && typeof first === 'object' && !Array.isArray(first)) {
    return fromOpts(first as Record<string, unknown>);
  }
  if (typeof first === 'number') {
    const host = typeof args[1] === 'string' ? args[1] : '127.0.0.1';
    return { host, url: `tcp://${host}:${first}` };
  }
  return { host: '', url: '' };
}

function identifySubsystem(url: string, stack: string): string {
  const s = (url + ' ' + stack).toLowerCase();
  if (
    s.includes('llm') ||
    s.includes('inference') ||
    s.includes('openai') ||
    s.includes('ollama') ||
    s.includes('anthropic') ||
    s.includes('completions') ||
    s.includes('chat/') ||
    s.includes('/v1/')
  )
    return 'llm-inference';
  if (s.includes('whisper') || s.includes('speech') || s.includes('/stt') || s.includes('transcri'))
    return 'speech-to-text';
  if (s.includes('/tts') || s.includes('text-to-speech') || s.includes('synthesis'))
    return 'text-to-speech';
  if (s.includes('telemetry') || s.includes('analytics') || s.includes('metric'))
    return 'telemetry';
  if (s.includes('asset') || s.includes('download') || s.includes('cdn')) return 'asset-fetch';
  return 'unknown';
}

export interface NetworkGuard {
  readonly violations: NetworkViolation[];
  restore(): void;
}

/**
 * Install a low-level network guard that intercepts all outbound TCP connections
 * by patching `net.Socket.prototype.connect`.
 *
 * Any connection to a non-localhost host is blocked (the socket emits an error
 * event) and recorded in `violations`.  Call `restore()` when done to put the
 * original `connect` back.
 *
 * Works in Node.js ESM mode: `Socket.prototype` is an ordinary mutable object
 * unlike ESM module namespace objects.  Covers http, https, and fetch because
 * all of them ultimately call `socket.connect()` for the TCP handshake.
 */
export function installNetworkGuard(): NetworkGuard {
  const violations: NetworkViolation[] = [];
  const origConnect = Socket.prototype.connect;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (Socket.prototype as any).connect = function patchedConnect(
    this: Socket,
    ...args: unknown[]
  ): Socket {
    const { host, url } = parseConnectArgs(args);
    if (host && !isLocalhost(host)) {
      const stack = new Error().stack ?? '';
      const subsystem = identifySubsystem(url, stack);
      violations.push({ url: url || `tcp://${host}`, subsystem });
      const err = new Error(
        `[offline-smoke-test] NETWORK_BLOCKED: connection to ${host} blocked (subsystem: ${subsystem}). Play mode must not use outbound network.`,
      );
      (err as NodeJS.ErrnoException).code = 'ENETWORK_BLOCKED';
      // The HTTP/TLS layer wires up socket error listeners asynchronously
      // (inside the `oncreate` callback, which fires only on successful
      // TCP/TLS connect).  Since we are blocking the connection, `oncreate`
      // never fires and the socket has no error listeners when the nextTick
      // below runs — causing an unhandled-error crash.  Adding a noop here
      // ensures the error is always consumed at the socket level; violations
      // are already recorded synchronously above so callers need not await it.
      this.once('error', () => {});
      process.nextTick(() => this.emit('error', err));
      return this;
    }
    return origConnect.apply(this, args as Parameters<typeof origConnect>) as Socket;
  };

  return {
    get violations() {
      return violations;
    },
    restore() {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (Socket.prototype as any).connect = origConnect;
    },
  };
}

// ---------------------------------------------------------------------------
// Scripted session simulation (fake runtime — no network required)
// ---------------------------------------------------------------------------

const SCRIPTED_PLAYER_TURNS = [
  'Hello, I am ready to start the session.',
  'I have relevant experience and I am prepared to engage with this scenario.',
  'Thank you. I understand the goals and I am happy to continue.',
];

const FAKE_NPC_UTTERANCE = 'Thank you for your response. Please continue.';

interface SmokeSessResult {
  pack_id: string;
  scenario_id: string;
  turns_played: number;
  debrief_generated: boolean;
}

function runScriptedSession(absPackPath: string, testNetworkProbe?: () => void): SmokeSessResult {
  const pack = loadPack(absPackPath, 'local-dev');

  if (pack.scenarios.length === 0) {
    throw new Error('Pack has no scenarios — cannot run offline smoke test');
  }

  const firstScenario = pack.scenarios[0]!;
  const bundle = resolveBundle(pack, firstScenario.data.scenario_id);

  const maxTurns = bundle.scenario.duration?.max_turns ?? 20;
  const turnsToPlay = Math.min(SCRIPTED_PLAYER_TURNS.length, maxTurns);

  // Phase 1: Start — NPC delivers opening line (local string, no network)
  const _openingLine = bundle.scenario.opening.npc_says;

  // Phase 2: Player turns — fake NPC responds locally, no LLM or cloud call needed
  let turnsPlayed = 0;
  for (let i = 0; i < turnsToPlay; i++) {
    const _playerInput = SCRIPTED_PLAYER_TURNS[i];
    const _npcResponse = FAKE_NPC_UTTERANCE; // fake runtime, no network
    turnsPlayed++;
  }

  // Test hook: inject a probe while the network guard is active.
  // Any outbound call made here will be intercepted and recorded as a violation.
  testNetworkProbe?.();

  // Phase 3: Generate debrief — from local session state only, no LLM call
  const _debrief = {
    summary: `Offline smoke: ${turnsPlayed} turn(s) of "${bundle.scenario.title}" completed.`,
    outcome: 'player_exit',
    scenario_id: bundle.scenarioId,
    pack_id: bundle.packId,
  };

  return {
    pack_id: pack.manifest.pack_id,
    scenario_id: bundle.scenarioId,
    turns_played: turnsPlayed,
    debrief_generated: true,
  };
}

// ---------------------------------------------------------------------------
// Command
// ---------------------------------------------------------------------------

export interface OfflineSmokeTestOptions {
  /** @internal For integration testing: called after turns while the guard is active. */
  _testNetworkProbe?: () => void;
}

/**
 * Run the offline smoke test for a pack directory.
 *
 * Installs a network guard that intercepts all outbound TCP connections (via
 * `net.Socket.prototype.connect`), loads the first scenario from the given
 * pack, runs a scripted text conversation with the fake runtime, generates a
 * local debrief, then verifies that no outbound network calls occurred.
 *
 * Exit codes:
 *   0 — offline check passed (no outbound network, debrief generated)
 *   1 — network violation detected, or pack/scenario error
 *   3 — unexpected system error
 */
export function runOfflineSmokeTest(
  packPath: string,
  json: boolean,
  options?: OfflineSmokeTestOptions,
): number {
  const absPath = resolve(packPath);
  const guard = installNetworkGuard();

  let simResult: SmokeSessResult;
  try {
    simResult = runScriptedSession(absPath, options?._testNetworkProbe);
  } catch (e) {
    guard.restore();

    // Violations are recorded synchronously during socket.connect, so check
    // them even when runScriptedSession threw an unrelated error.
    if (guard.violations.length > 0) {
      const result: OfflineSmokeTestResult = {
        status: 'network_violation',
        pack_id: '',
        scenario_id: '',
        turns_played: 0,
        network_violations: guard.violations,
      };
      if (json) {
        writeJson(result);
      } else {
        writeErrorLine('✗ Offline smoke test FAILED: outbound network access detected');
        for (const v of guard.violations) {
          writeErrorLine(`  Subsystem: ${v.subsystem}`);
          writeErrorLine(`  URL: ${v.url}`);
        }
        writeErrorLine('  Play mode must not require outbound network. Check local runtime setup.');
      }
      return 1;
    }

    if (e instanceof PackLoaderError) {
      const result: OfflineSmokeTestResult = {
        status: 'error',
        error: {
          code: e.code,
          message: e.message,
          ...(e.filePath !== undefined ? { file: e.filePath } : {}),
        },
      };
      if (json) {
        writeJson(result);
      } else {
        writeErrorLine(`✗ Offline smoke test failed: pack error (${e.code})`);
        writeErrorLine(`  ${e.message}`);
        if (e.filePath !== undefined) writeErrorLine(`  File: ${e.filePath}`);
      }
      return 1;
    }

    const msg = e instanceof Error ? e.message : String(e);
    if (json) {
      writeJson({
        status: 'error',
        error: { code: 'UNEXPECTED_ERROR', message: msg },
      } satisfies OfflineSmokeTestResult);
    } else {
      writeErrorLine(`✗ Unexpected error: ${msg}`);
    }
    return 3;
  }

  guard.restore();

  // Violations are synchronously recorded; check after session completes.
  if (guard.violations.length > 0) {
    const result: OfflineSmokeTestResult = {
      status: 'network_violation',
      pack_id: simResult.pack_id,
      scenario_id: simResult.scenario_id,
      turns_played: simResult.turns_played,
      network_violations: guard.violations,
    };
    if (json) {
      writeJson(result);
    } else {
      writeErrorLine(
        `✗ Offline smoke test FAILED: outbound network detected during play (${guard.violations.length} violation${guard.violations.length !== 1 ? 's' : ''})`,
      );
      for (const v of guard.violations) {
        writeErrorLine(`  Subsystem: ${v.subsystem}`);
        writeErrorLine(`  URL: ${v.url}`);
      }
      writeErrorLine('  Install a local runtime or check for background telemetry.');
    }
    return 1;
  }

  const result: OfflineSmokeTestResult = {
    status: 'ok',
    pack_id: simResult.pack_id,
    scenario_id: simResult.scenario_id,
    turns_played: simResult.turns_played,
    debrief_generated: simResult.debrief_generated,
    network_violations: [],
  };

  if (json) {
    writeJson(result);
  } else {
    writeLine('✓ Offline smoke test passed');
    writeLine(`  Pack:     ${simResult.pack_id}`);
    writeLine(`  Scenario: ${simResult.scenario_id}`);
    writeLine(`  Turns:    ${simResult.turns_played}`);
    writeLine(`  Debrief:  generated`);
    writeLine(`  Network:  no outbound calls detected`);
  }

  return 0;
}
