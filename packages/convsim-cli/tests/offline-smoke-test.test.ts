// SPDX-License-Identifier: Apache-2.0
import { mkdtempSync, rmSync, writeFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { tmpdir } from 'node:os';
import { Socket } from 'node:net';
import * as http from 'node:http';
import * as https from 'node:https';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

import { runOfflineSmokeTest, installNetworkGuard } from '../src/commands/offline-smoke-test.js';

// ---------------------------------------------------------------------------
// Pack fixtures
// ---------------------------------------------------------------------------

const VALID_MANIFEST = `schema_version: "0.1"
pack_id: test.smoke_pack
name: Smoke Test Pack
version: 1.0.0
description: Minimal pack for offline smoke testing.
author: Smoke Test Suite
license: MIT
content_rating: PG
safety:
  policy: safety/policy.yaml
`;

const VALID_SAFETY = `schema_version: "0.1"
policy_id: smoke_safety
content_rating_cap: PG
content_categories:
  nsfw_sexual: block
  real_person_impersonation: block
  instructional_criminal: block
  crisis_content: redirect
redirect_message: "Redirected."
`;

const VALID_NPC = `schema_version: "0.1"
npc_id: smoke_npc
display_name: Smoke NPC
archetype: interviewer
fictional: true
age_band: adult
public_persona:
  occupation: Test Interviewer
  speaking_style: Neutral
  demeanor: Professional
private_persona: {}
`;

const VALID_RUBRIC = `schema_version: "0.1"
rubric_id: smoke_rubric
title: Smoke Rubric
dimensions:
  - id: clarity
    name: Clarity
    description: How clearly the player communicates.
    scoring:
      low: Unclear
      medium: Adequate
      high: Excellent
`;

const VALID_SCENARIO = `schema_version: "0.1"
scenario_id: smoke_scenario
title: Smoke Test Scenario
summary: A minimal scenario used only for offline smoke testing.
player_role:
  label: Tester
  brief: You are verifying the offline smoke test.
npc:
  ref: ../npcs/smoke_npc.yaml
rubric:
  ref: ../rubrics/smoke_rubric.yaml
duration:
  max_turns: 10
opening:
  npc_says: "Hello. Let us begin."
goals:
  player_visible:
    - Complete the offline smoke test
`;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeValidPackDir(): string {
  const root = mkdtempSync(join(tmpdir(), 'convsim-smoke-pack-'));
  for (const sub of ['scenarios', 'npcs', 'rubrics', 'safety']) {
    mkdirSync(join(root, sub));
  }
  writeFileSync(join(root, 'manifest.yaml'), VALID_MANIFEST);
  writeFileSync(join(root, 'safety', 'policy.yaml'), VALID_SAFETY);
  writeFileSync(join(root, 'npcs', 'smoke_npc.yaml'), VALID_NPC);
  writeFileSync(join(root, 'rubrics', 'smoke_rubric.yaml'), VALID_RUBRIC);
  writeFileSync(join(root, 'scenarios', 'smoke_scenario.yaml'), VALID_SCENARIO);
  return root;
}

function makeBrokenPackDir(): string {
  const root = mkdtempSync(join(tmpdir(), 'convsim-smoke-broken-'));
  writeFileSync(join(root, 'manifest.yaml'), 'schema_version: "0.1"\nnot_valid: true\n');
  return root;
}

function captureOutput(fn: () => unknown): { stdout: string; stderr: string } {
  let stdout = '';
  let stderr = '';
  const spyOut = vi.spyOn(process.stdout, 'write').mockImplementation((d) => {
    stdout += String(d);
    return true;
  });
  const spyErr = vi.spyOn(process.stderr, 'write').mockImplementation((d) => {
    stderr += String(d);
    return true;
  });
  try {
    fn();
  } finally {
    spyOut.mockRestore();
    spyErr.mockRestore();
  }
  return { stdout, stderr };
}

/**
 * Simulate an outbound HTTPS connection that the guard can intercept.
 * The connection attempt is recorded synchronously in Socket.prototype.connect
 * before the request error fires asynchronously.
 */
function makeOutboundCall(url: string): void {
  const req = https.request(url);
  req.on('error', () => {}); // silence the async NETWORK_BLOCKED error event
}

// ---------------------------------------------------------------------------
// Test lifecycle
// ---------------------------------------------------------------------------

let tempDirs: string[] = [];

beforeEach(() => {
  tempDirs = [];
});

afterEach(() => {
  vi.restoreAllMocks();
  for (const d of tempDirs) {
    rmSync(d, { recursive: true, force: true });
  }
});

function track(dir: string): string {
  tempDirs.push(dir);
  return dir;
}

// ===========================================================================
// installNetworkGuard — unit tests
// ===========================================================================

describe('installNetworkGuard — guard is patchable', () => {
  it('replaces Socket.prototype.connect while active', () => {
    const origConnect = Socket.prototype.connect;
    const guard = installNetworkGuard();
    expect(Socket.prototype.connect).not.toBe(origConnect);
    guard.restore();
    expect(Socket.prototype.connect).toBe(origConnect);
  });

  it('restores Socket.prototype.connect after restore()', () => {
    const origConnect = Socket.prototype.connect;
    const guard = installNetworkGuard();
    guard.restore();
    expect(Socket.prototype.connect).toBe(origConnect);
  });

  it('starts with an empty violations array', () => {
    const guard = installNetworkGuard();
    expect(guard.violations).toHaveLength(0);
    guard.restore();
  });
});

describe('installNetworkGuard — outbound calls are blocked and recorded', () => {
  it('records a violation for an outbound https request', () => {
    const guard = installNetworkGuard();
    makeOutboundCall('https://example.com/test');
    guard.restore();
    expect(guard.violations).toHaveLength(1);
    expect(guard.violations[0]!.url).toContain('example.com');
  });

  it('records a violation for an outbound http request', () => {
    const guard = installNetworkGuard();
    const req = http.request('http://api.example.com/data');
    req.on('error', () => {});
    guard.restore();
    expect(guard.violations).toHaveLength(1);
    expect(guard.violations[0]!.url).toContain('api.example.com');
  });

  it('records a violation for an outbound built-in fetch() call', async () => {
    // Node's global fetch (undici) ultimately opens its TCP connection through
    // net.Socket.prototype.connect, so the guard must catch it too — this is the
    // path a cloud LLM/transcription client would most likely use. Subsystem
    // attribution for fetch relies on the hostname (undici does not expose the
    // request path at the socket layer), so use a host that carries the signal.
    const guard = installNetworkGuard();
    await fetch('https://llm-inference.example.com/v1/completions').catch(() => {});
    guard.restore();
    expect(guard.violations).toHaveLength(1);
    expect(guard.violations[0]!.url).toContain('llm-inference.example.com');
    expect(guard.violations[0]!.subsystem).toBe('llm-inference');
  });

  it('accumulates multiple violations', () => {
    const guard = installNetworkGuard();
    makeOutboundCall('https://llm.cloud.example.com/v1/completions');
    makeOutboundCall('https://telemetry.example.com/events');
    makeOutboundCall('https://cdn.example.com/asset.mp3');
    guard.restore();
    expect(guard.violations).toHaveLength(3);
  });

  it('violation entries have url and subsystem strings', () => {
    const guard = installNetworkGuard();
    makeOutboundCall('https://external.example.com/api');
    guard.restore();
    expect(typeof guard.violations[0]!.url).toBe('string');
    expect(typeof guard.violations[0]!.subsystem).toBe('string');
    expect(guard.violations[0]!.url.length).toBeGreaterThan(0);
  });
});

describe('installNetworkGuard — localhost is allowed', () => {
  it('does not record a violation for a request to 127.0.0.1', () => {
    const guard = installNetworkGuard();
    // The connection will fail (no server), but the guard should not record it as a violation.
    const req = http.request({ hostname: '127.0.0.1', port: 19998, path: '/' });
    req.on('error', () => {});
    req.end();
    guard.restore();
    expect(guard.violations).toHaveLength(0);
  });

  it('does not record a violation for a request to localhost', () => {
    const guard = installNetworkGuard();
    // The connection will fail (no server), but the guard should not record it.
    const req = http.request({ hostname: 'localhost', port: 19999, path: '/' });
    req.on('error', () => {});
    req.end();
    guard.restore();
    expect(guard.violations).toHaveLength(0);
  });

  it('does not record a violation for a request to ::1 (IPv6 loopback)', () => {
    const guard = installNetworkGuard();
    // ::1 splits to '' on ':', so the pre-fix code missed this — verify the guard allows it.
    const req = http.request({ hostname: '::1', port: 19997, path: '/' });
    req.on('error', () => {});
    req.end();
    guard.restore();
    expect(guard.violations).toHaveLength(0);
  });
});

describe('installNetworkGuard — subsystem identification', () => {
  it('identifies a URL containing "llm" as llm-inference', () => {
    const guard = installNetworkGuard();
    makeOutboundCall('https://llm.api.example.com/generate');
    guard.restore();
    expect(guard.violations[0]?.subsystem).toBe('llm-inference');
  });

  it('identifies a URL containing "completions" as llm-inference', () => {
    const guard = installNetworkGuard();
    makeOutboundCall('https://cloud.example.com/v1/completions');
    guard.restore();
    expect(guard.violations[0]?.subsystem).toBe('llm-inference');
  });

  it('identifies a URL containing "stt" as speech-to-text', () => {
    const guard = installNetworkGuard();
    makeOutboundCall('https://stt.cloud.example.com/transcribe');
    guard.restore();
    expect(guard.violations[0]?.subsystem).toBe('speech-to-text');
  });

  it('identifies a URL containing "telemetry" as telemetry', () => {
    const guard = installNetworkGuard();
    makeOutboundCall('https://telemetry.example.com/events');
    guard.restore();
    expect(guard.violations[0]?.subsystem).toBe('telemetry');
  });

  it('falls back to "unknown" for an unrecognised URL', () => {
    const guard = installNetworkGuard();
    makeOutboundCall('https://mystery.host.example.com/data');
    guard.restore();
    expect(guard.violations[0]?.subsystem).toBe('unknown');
  });
});

// ===========================================================================
// runOfflineSmokeTest — happy path
// ===========================================================================

describe('offline-smoke-test — valid pack', () => {
  it('returns exit code 0', () => {
    const packDir = track(makeValidPackDir());
    const code = runOfflineSmokeTest(packDir, false);
    expect(code).toBe(0);
  });

  it('human output shows pass indicators', () => {
    const packDir = track(makeValidPackDir());
    const { stdout } = captureOutput(() => runOfflineSmokeTest(packDir, false));
    expect(stdout).toContain('✓');
    expect(stdout).toContain('Offline smoke test passed');
    expect(stdout).toContain('test.smoke_pack');
    expect(stdout).toContain('smoke_scenario');
    expect(stdout).toContain('no outbound calls');
  });

  it('JSON output has status ok with expected fields', () => {
    const packDir = track(makeValidPackDir());
    let captured = '';
    const spy = vi.spyOn(process.stdout, 'write').mockImplementation((d) => {
      captured += String(d);
      return true;
    });
    runOfflineSmokeTest(packDir, true);
    spy.mockRestore();
    const result = JSON.parse(captured) as Record<string, unknown>;
    expect(result['status']).toBe('ok');
    expect(result['pack_id']).toBe('test.smoke_pack');
    expect(result['scenario_id']).toBe('smoke_scenario');
    expect(typeof result['turns_played']).toBe('number');
    expect((result['turns_played'] as number)).toBeGreaterThan(0);
    expect(result['debrief_generated']).toBe(true);
    expect(Array.isArray(result['network_violations'])).toBe(true);
    expect((result['network_violations'] as unknown[]).length).toBe(0);
  });

  it('plays at least one scripted turn', () => {
    const packDir = track(makeValidPackDir());
    let captured = '';
    const spy = vi.spyOn(process.stdout, 'write').mockImplementation((d) => {
      captured += String(d);
      return true;
    });
    runOfflineSmokeTest(packDir, true);
    spy.mockRestore();
    const result = JSON.parse(captured) as { turns_played: number };
    expect(result.turns_played).toBeGreaterThanOrEqual(1);
  });

  it('restores Socket.prototype.connect after a successful run', () => {
    const packDir = track(makeValidPackDir());
    const origConnect = Socket.prototype.connect;
    runOfflineSmokeTest(packDir, false);
    expect(Socket.prototype.connect).toBe(origConnect);
  });
});

// ===========================================================================
// runOfflineSmokeTest — network violation detection
// ===========================================================================

describe('offline-smoke-test — network violation via test probe', () => {
  it('returns exit code 1 when probe makes an outbound https call', () => {
    const packDir = track(makeValidPackDir());
    const code = runOfflineSmokeTest(packDir, false, {
      _testNetworkProbe() {
        makeOutboundCall('https://cloud-llm.example.com/v1/completions');
      },
    });
    expect(code).toBe(1);
  });

  it('returns exit code 1 when probe makes an outbound http call', () => {
    const packDir = track(makeValidPackDir());
    const code = runOfflineSmokeTest(packDir, false, {
      _testNetworkProbe() {
        const req = http.request('http://telemetry.example.com/events');
        req.on('error', () => {});
      },
    });
    expect(code).toBe(1);
  });

  it('human output shows the violation URL and failure indicator', () => {
    const packDir = track(makeValidPackDir());
    const { stderr } = captureOutput(() =>
      runOfflineSmokeTest(packDir, false, {
        _testNetworkProbe() {
          makeOutboundCall('https://stt-cloud.example.com/transcribe');
        },
      }),
    );
    expect(stderr).toContain('✗');
    expect(stderr).toContain('FAILED');
    expect(stderr).toContain('stt-cloud.example.com');
  });

  it('JSON output has status network_violation with a violations array', () => {
    const packDir = track(makeValidPackDir());
    let captured = '';
    const spy = vi.spyOn(process.stdout, 'write').mockImplementation((d) => {
      captured += String(d);
      return true;
    });
    runOfflineSmokeTest(packDir, true, {
      _testNetworkProbe() {
        makeOutboundCall('https://cloud.example.com/api');
      },
    });
    spy.mockRestore();
    const result = JSON.parse(captured) as Record<string, unknown>;
    expect(result['status']).toBe('network_violation');
    const violations = result['network_violations'] as Array<{ url: string; subsystem: string }>;
    expect(Array.isArray(violations)).toBe(true);
    expect(violations.length).toBeGreaterThan(0);
    expect(typeof violations[0]!.url).toBe('string');
    expect(typeof violations[0]!.subsystem).toBe('string');
  });

  it('violation URL appears in JSON violations array', () => {
    const packDir = track(makeValidPackDir());
    let captured = '';
    const spy = vi.spyOn(process.stdout, 'write').mockImplementation((d) => {
      captured += String(d);
      return true;
    });
    runOfflineSmokeTest(packDir, true, {
      _testNetworkProbe() {
        makeOutboundCall('https://inference.cloud.example.com/generate');
      },
    });
    spy.mockRestore();
    const result = JSON.parse(captured) as Record<string, unknown>;
    const violations = result['network_violations'] as Array<{ url: string }>;
    const found = violations.some((v) => v.url.includes('inference.cloud.example.com'));
    expect(found).toBe(true);
  });

  it('restores Socket.prototype.connect even after a violation', () => {
    const packDir = track(makeValidPackDir());
    const origConnect = Socket.prototype.connect;
    runOfflineSmokeTest(packDir, false, {
      _testNetworkProbe() {
        makeOutboundCall('https://blocked.example.com/api');
      },
    });
    expect(Socket.prototype.connect).toBe(origConnect);
  });
});

// ===========================================================================
// runOfflineSmokeTest — error cases
// ===========================================================================

describe('offline-smoke-test — broken pack', () => {
  it('returns exit code 1 for a pack that fails schema validation', () => {
    const packDir = track(makeBrokenPackDir());
    const code = runOfflineSmokeTest(packDir, false);
    expect(code).toBe(1);
  });

  it('human output contains failure indicator', () => {
    const packDir = track(makeBrokenPackDir());
    const { stderr } = captureOutput(() => runOfflineSmokeTest(packDir, false));
    expect(stderr).toContain('✗');
  });

  it('JSON output has status error with code and message', () => {
    const packDir = track(makeBrokenPackDir());
    let captured = '';
    const spy = vi.spyOn(process.stdout, 'write').mockImplementation((d) => {
      captured += String(d);
      return true;
    });
    runOfflineSmokeTest(packDir, true);
    spy.mockRestore();
    const result = JSON.parse(captured) as Record<string, unknown>;
    expect(result['status']).toBe('error');
    const err = result['error'] as Record<string, unknown>;
    expect(typeof err['code']).toBe('string');
    expect(typeof err['message']).toBe('string');
  });

  it('returns exit code 1 for a non-existent path', () => {
    const code = runOfflineSmokeTest('/tmp/this-does-not-exist-convsim-smoke', false);
    expect(code).toBe(1);
  });

  it('restores Socket.prototype.connect even on pack error', () => {
    const packDir = track(makeBrokenPackDir());
    const origConnect = Socket.prototype.connect;
    runOfflineSmokeTest(packDir, false);
    expect(Socket.prototype.connect).toBe(origConnect);
  });
});

// ===========================================================================
// runOfflineSmokeTest — official packs (acceptance criterion)
// ===========================================================================

describe('offline-smoke-test — official packs', () => {
  const repoRoot = fileURLToPath(new URL('../../../', import.meta.url));
  const jobInterviewPack = join(repoRoot, 'packs', 'official', 'job-interview-basic');

  it('passes for the first official pack (job-interview-basic)', () => {
    const code = runOfflineSmokeTest(jobInterviewPack, false);
    expect(code).toBe(0);
  });

  it('JSON output is ok for the first official pack', () => {
    let captured = '';
    const spy = vi.spyOn(process.stdout, 'write').mockImplementation((d) => {
      captured += String(d);
      return true;
    });
    runOfflineSmokeTest(jobInterviewPack, true);
    spy.mockRestore();
    const result = JSON.parse(captured) as Record<string, unknown>;
    expect(result['status']).toBe('ok');
    expect(typeof result['pack_id']).toBe('string');
    expect(typeof result['scenario_id']).toBe('string');
    expect((result['turns_played'] as number)).toBeGreaterThan(0);
    expect(result['debrief_generated']).toBe(true);
    expect((result['network_violations'] as unknown[]).length).toBe(0);
  });

  it('Socket.prototype.connect is restored after the official pack run', () => {
    const origConnect = Socket.prototype.connect;
    runOfflineSmokeTest(jobInterviewPack, true);
    expect(Socket.prototype.connect).toBe(origConnect);
  });

  const difficultConvPack = join(repoRoot, 'packs', 'official', 'difficult-conversations');

  it('passes for the difficult-conversations pack', () => {
    const code = runOfflineSmokeTest(difficultConvPack, false);
    expect(code).toBe(0);
  });

  it('JSON output is ok for the difficult-conversations pack', () => {
    let captured = '';
    const spy = vi.spyOn(process.stdout, 'write').mockImplementation((d) => {
      captured += String(d);
      return true;
    });
    runOfflineSmokeTest(difficultConvPack, true);
    spy.mockRestore();
    const result = JSON.parse(captured) as Record<string, unknown>;
    expect(result['status']).toBe('ok');
    expect(result['pack_id']).toBe('official.difficult_conversations');
    expect(typeof result['scenario_id']).toBe('string');
    expect((result['turns_played'] as number)).toBeGreaterThan(0);
    expect(result['debrief_generated']).toBe(true);
    expect((result['network_violations'] as unknown[]).length).toBe(0);
  });

  it('Socket.prototype.connect is restored after the difficult-conversations pack run', () => {
    const origConnect = Socket.prototype.connect;
    runOfflineSmokeTest(difficultConvPack, true);
    expect(Socket.prototype.connect).toBe(origConnect);
  });
});
