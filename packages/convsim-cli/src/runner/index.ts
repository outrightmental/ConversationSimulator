// SPDX-License-Identifier: Apache-2.0
import type { LoadedPack, RawFixtureTurn } from '@convsim/pack-loader';
import { loadFixtures, resolveBundle } from '@convsim/pack-loader';
import { resolvePath } from './path-resolver.js';
import { evaluateCheck } from './check-evaluator.js';
import { runFakeTurn } from './fake-runtime.js';
import type { FakeTurnOutput } from './fake-runtime.js';
import type {
  FailureReport,
  FixtureRunResult,
  PackTestRunResult,
} from './types.js';

export type { PackTestRunResult, FixtureRunResult, FailureReport };

/**
 * Run all pack-test fixtures found in a loaded pack's `tests/` directory.
 *
 * Each fixture is run with the fake runtime (deterministic, no model required).
 * Fixtures whose scenario_id is not found in the pack are reported as skipped.
 *
 * Returns a summary including pass, fail, and skip counts. The overall run
 * fails (failed > 0) only when assertions or structural expectations are not
 * met; skips do not count as failures.
 */
export function runPackTests(pack: LoadedPack): PackTestRunResult {
  const { fixtures, errors: loadErrors } = loadFixtures(pack.packRoot);

  const results: FixtureRunResult[] = [];

  for (const err of loadErrors) {
    results.push({
      fixture_id: err.filePath,
      scenario_id: '(unknown)',
      description: `Failed to load: ${err.error}`,
      status: 'failed',
      failures: [
        {
          kind: 'load_error',
          description: err.error,
        },
      ],
      static_assertion_count: 0,
      turn_count: 0,
      mode: 'fake',
    });
  }

  for (const { fixture } of fixtures) {
    results.push(runFixture(pack, fixture));
  }

  const passed = results.filter((r) => r.status === 'passed').length;
  const failed = results.filter((r) => r.status === 'failed').length;
  const skipped = results.filter((r) => r.status === 'skipped').length;

  return {
    pack_id: pack.manifest.pack_id,
    pack_name: pack.manifest.name,
    fixture_count: results.length,
    passed,
    failed,
    skipped,
    fixtures: results,
  };
}

function runFixture(
  pack: LoadedPack,
  fixture: import('@convsim/pack-loader').RawFixture,
): FixtureRunResult {
  // Find the scenario — if missing, skip rather than fail
  let bundle: import('@convsim/pack-loader').ResolvedBundle;
  try {
    bundle = resolveBundle(pack, fixture.scenario_id);
  } catch {
    return {
      fixture_id: fixture.fixture_id,
      scenario_id: fixture.scenario_id,
      description: fixture.description,
      status: 'skipped',
      failures: [],
      static_assertion_count: 0,
      turn_count: fixture.turns.length,
      mode: 'fake',
      skip_reason: `Scenario "${fixture.scenario_id}" not found in pack`,
    };
  }

  const docs = {
    scenario: bundle.scenario as Record<string, unknown>,
    npc: bundle.npc as Record<string, unknown>,
    rubric: bundle.rubric as Record<string, unknown>,
    safety: bundle.safety as Record<string, unknown>,
    manifest: pack.manifest as Record<string, unknown>,
  };

  const failures: FailureReport[] = [];

  // Static assertions — checked against loaded pack documents (no runtime)
  const staticAssertions = fixture.static_assertions ?? [];
  for (const assertion of staticAssertions) {
    const value = resolvePath(docs, assertion.path);
    if (!evaluateCheck(value, assertion.check)) {
      failures.push({
        kind: 'static_assertion',
        description: assertion.description,
        path: assertion.path,
        check: assertion.check,
        actual: value,
      });
    }
  }

  // Turn expectations — checked against fake runtime output
  for (const turn of fixture.turns) {
    const fakeOutput = runFakeTurn(bundle.scenario, turn.turn, turn.player_input);
    for (const f of checkTurnExpectations(turn, fakeOutput)) {
      failures.push(f);
    }
  }

  return {
    fixture_id: fixture.fixture_id,
    scenario_id: fixture.scenario_id,
    description: fixture.description,
    status: failures.length === 0 ? 'passed' : 'failed',
    failures,
    static_assertion_count: staticAssertions.length,
    turn_count: fixture.turns.length,
    mode: 'fake',
  };
}

function checkTurnExpectations(
  turn: RawFixtureTurn,
  output: FakeTurnOutput,
): FailureReport[] {
  const failures: FailureReport[] = [];
  const expect = turn.expect;
  if (!expect) return failures;

  if (expect.state_delta_contains) {
    for (const varName of expect.state_delta_contains) {
      if (!(varName in output.state_delta)) {
        failures.push({
          kind: 'turn_expectation',
          description: `Turn ${turn.turn}: state_delta missing declared variable "${varName}"`,
          turn: turn.turn,
          expectation: 'state_delta_contains',
          expected: varName,
          actual: Object.keys(output.state_delta),
        });
      }
    }
  }

  // npc_emotion_not: fake runtime produces no emotion (null), so this assertion
  // is trivially satisfied — recorded only when a real runtime later sets emotion.

  if (expect.session_control !== undefined) {
    if (output.session_control !== expect.session_control) {
      failures.push({
        kind: 'turn_expectation',
        description: `Turn ${turn.turn}: session_control expected "${expect.session_control}", got "${output.session_control}"`,
        turn: turn.turn,
        expectation: 'session_control',
        expected: expect.session_control,
        actual: output.session_control,
      });
    }
  }

  if (expect.safety_status !== undefined) {
    if (output.safety_status !== expect.safety_status) {
      failures.push({
        kind: 'turn_expectation',
        description: `Turn ${turn.turn}: safety_status expected "${expect.safety_status}", got "${output.safety_status}"`,
        turn: turn.turn,
        expectation: 'safety_status',
        expected: expect.safety_status,
        actual: output.safety_status,
      });
    }
  }

  return failures;
}
