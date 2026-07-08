// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest';
import { evaluateCheck } from '../src/runner/check-evaluator.js';
import { resolvePath } from '../src/runner/path-resolver.js';
import { runFakeTurn } from '../src/runner/fake-runtime.js';
import type { DocBundle } from '../src/runner/path-resolver.js';
import type { RawScenario } from '@convsim/pack-loader';

// ---------------------------------------------------------------------------
// check-evaluator
// ---------------------------------------------------------------------------

describe('evaluateCheck — non_empty_string', () => {
  it('passes for a non-empty string', () => {
    expect(evaluateCheck('hello', 'non_empty_string')).toBe(true);
  });
  it('fails for an empty string', () => {
    expect(evaluateCheck('', 'non_empty_string')).toBe(false);
  });
  it('fails for a non-string value', () => {
    expect(evaluateCheck(42, 'non_empty_string')).toBe(false);
    expect(evaluateCheck(null, 'non_empty_string')).toBe(false);
  });
});

describe('evaluateCheck — min_length_1', () => {
  it('passes for an array with items', () => {
    expect(evaluateCheck(['a'], 'min_length_1')).toBe(true);
    expect(evaluateCheck(['a', 'b'], 'min_length_1')).toBe(true);
  });
  it('fails for an empty array', () => {
    expect(evaluateCheck([], 'min_length_1')).toBe(false);
  });
  it('fails for a non-array', () => {
    expect(evaluateCheck('hello', 'min_length_1')).toBe(false);
  });
});

describe('evaluateCheck — equals', () => {
  it('passes for matching boolean true', () => {
    expect(evaluateCheck(true, 'equals true')).toBe(true);
  });
  it('passes for matching boolean false', () => {
    expect(evaluateCheck(false, 'equals false')).toBe(true);
  });
  it('passes for matching string', () => {
    expect(evaluateCheck('block', 'equals block')).toBe(true);
  });
  it('passes for matching number', () => {
    expect(evaluateCheck(42, 'equals 42')).toBe(true);
  });
  it('fails for mismatched value', () => {
    expect(evaluateCheck('allow', 'equals block')).toBe(false);
    expect(evaluateCheck(false, 'equals true')).toBe(false);
  });
});

describe('evaluateCheck — contains', () => {
  it('passes when array contains the needle', () => {
    expect(evaluateCheck(['a', 'b', 'c'], 'contains b')).toBe(true);
  });
  it('passes when string contains the needle', () => {
    expect(evaluateCheck('scenarios/foo.yaml', 'contains scenarios/foo.yaml')).toBe(true);
  });
  it('fails when array does not contain needle', () => {
    expect(evaluateCheck(['x', 'y'], 'contains z')).toBe(false);
  });
});

describe('evaluateCheck — key=value AND conditions', () => {
  it('passes when all conditions match', () => {
    const value = { type: 'variable_above', variable: 'impression', threshold: 70 };
    expect(evaluateCheck(value, 'type=variable_above AND variable=impression AND threshold=70')).toBe(true);
  });
  it('passes for subset conditions', () => {
    const value = { type: 'variable_above', variable: 'impression' };
    expect(evaluateCheck(value, 'type=variable_above AND variable=impression')).toBe(true);
  });
  it('fails when a condition does not match', () => {
    const value = { type: 'variable_above', variable: 'rapport' };
    expect(evaluateCheck(value, 'type=variable_above AND variable=impression')).toBe(false);
  });
  it('fails for non-object value', () => {
    expect(evaluateCheck('hello', 'type=variable_above')).toBe(false);
  });
  it('parses numeric threshold correctly', () => {
    const value = { type: 'variable_above', variable: 'count', threshold: 2 };
    expect(evaluateCheck(value, 'type=variable_above AND variable=count AND threshold=2')).toBe(true);
    // String '2' should not match numeric 2 via strict equality...
    // but the parsed literal for '2' is the number 2, so it matches
  });
});

// ---------------------------------------------------------------------------
// path-resolver
// ---------------------------------------------------------------------------

const SAMPLE_DOCS: DocBundle = {
  scenario: {
    opening: { npc_says: 'Hello from the scenario.' },
    events: [
      { id: 'rambling_redirect', when: { type: 'variable_above', variable: 'rambling_count', threshold: 2 } },
      { id: 'success_event', when: { type: 'variable_above', variable: 'impression', threshold: 70 } },
    ],
    ending_conditions: {
      success: { type: 'variable_above', variable: 'impression', threshold: 70 },
      failure: { type: 'variable_below', variable: 'impression', threshold: 15 },
    },
    state: {
      variables: {
        impression: { min: 0, max: 100, default: 50 },
        rambling_count: { min: 0, max: 10, default: 0 },
      },
    },
  },
  npc: { fictional: true, npc_id: 'test_npc', display_name: 'Test NPC' },
  rubric: { rubric_id: 'test_rubric', dimensions: [{ id: 'accuracy', name: 'Accuracy' }] },
  safety: { content_categories: { nsfw_sexual: 'block', crisis_content: 'redirect' } },
  manifest: { pack_id: 'test.pack', entry_scenarios: ['scenarios/main.yaml'] },
};

describe('resolvePath — scenario fields', () => {
  it('resolves a nested path in the scenario', () => {
    expect(resolvePath(SAMPLE_DOCS, 'opening.npc_says')).toBe('Hello from the scenario.');
  });
  it('resolves a top-level array', () => {
    expect(Array.isArray(resolvePath(SAMPLE_DOCS, 'events'))).toBe(true);
  });
  it('resolves a nested path within ending_conditions', () => {
    const val = resolvePath(SAMPLE_DOCS, 'ending_conditions.success') as Record<string, unknown>;
    expect(val['type']).toBe('variable_above');
  });
  it('returns undefined for a non-existent path', () => {
    expect(resolvePath(SAMPLE_DOCS, 'does_not_exist.field')).toBeUndefined();
  });
});

describe('resolvePath — bracket selector', () => {
  it('finds the correct array element by id', () => {
    const val = resolvePath(SAMPLE_DOCS, 'events[id=rambling_redirect]') as Record<string, unknown>;
    expect(val['id']).toBe('rambling_redirect');
  });
  it('resolves a sub-path after a bracket selector', () => {
    const val = resolvePath(SAMPLE_DOCS, 'events[id=rambling_redirect].when') as Record<string, unknown>;
    expect(val['type']).toBe('variable_above');
    expect(val['variable']).toBe('rambling_count');
    expect(val['threshold']).toBe(2);
  });
  it('returns undefined when selector matches nothing', () => {
    expect(resolvePath(SAMPLE_DOCS, 'events[id=no_such_event]')).toBeUndefined();
  });
});

describe('resolvePath — alternate root documents', () => {
  it('resolves npc.fictional', () => {
    expect(resolvePath(SAMPLE_DOCS, 'npc.fictional')).toBe(true);
  });
  it('resolves safety.content_categories.nsfw_sexual', () => {
    expect(resolvePath(SAMPLE_DOCS, 'safety.content_categories.nsfw_sexual')).toBe('block');
  });
  it('resolves manifest.entry_scenarios', () => {
    const val = resolvePath(SAMPLE_DOCS, 'manifest.entry_scenarios');
    expect(Array.isArray(val)).toBe(true);
    expect((val as string[]).includes('scenarios/main.yaml')).toBe(true);
  });
  it('resolves rubric.dimensions', () => {
    expect(Array.isArray(resolvePath(SAMPLE_DOCS, 'rubric.dimensions'))).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// fake-runtime
// ---------------------------------------------------------------------------

const SAMPLE_SCENARIO: RawScenario = {
  schema_version: '0.1',
  scenario_id: 'test_scenario',
  title: 'Test',
  summary: 'Test scenario',
  player_role: { label: 'Tester', brief: 'You are testing.' },
  npc: { ref: '../npcs/npc.yaml' },
  rubric: { ref: '../rubrics/rubric.yaml' },
  duration: { max_turns: 10 },
  opening: { npc_says: 'Hello.' },
  goals: { player_visible: ['Test'] },
  state: {
    variables: {
      impression: { min: 0, max: 100, default: 50 },
      rapport: { min: 0, max: 100, default: 40 },
    },
  },
};

describe('runFakeTurn', () => {
  it('returns continue_session and safety_status ok', () => {
    const out = runFakeTurn(SAMPLE_SCENARIO, 1, 'Hello.');
    expect(out.session_control).toBe('continue_session');
    expect(out.safety_status).toBe('ok');
  });

  it('includes all declared state variables in state_delta', () => {
    const out = runFakeTurn(SAMPLE_SCENARIO, 1, 'Hello.');
    expect('impression' in out.state_delta).toBe(true);
    expect('rapport' in out.state_delta).toBe(true);
  });

  it('uses default values in state_delta', () => {
    const out = runFakeTurn(SAMPLE_SCENARIO, 1, 'Hello.');
    expect(out.state_delta['impression']).toBe(50);
    expect(out.state_delta['rapport']).toBe(40);
  });

  it('sets npc_emotion to null (no model)', () => {
    const out = runFakeTurn(SAMPLE_SCENARIO, 1, 'Hello.');
    expect(out.npc_emotion).toBeNull();
  });

  it('echoes turn and player_input', () => {
    const out = runFakeTurn(SAMPLE_SCENARIO, 3, 'Test input');
    expect(out.turn).toBe(3);
    expect(out.player_input).toBe('Test input');
  });

  it('returns empty state_delta for a scenario with no state', () => {
    const noState: RawScenario = { ...SAMPLE_SCENARIO, state: undefined };
    const out = runFakeTurn(noState, 1, 'Hello.');
    expect(out.state_delta).toEqual({});
  });
});

// ---------------------------------------------------------------------------
// Golden snapshot: smoke_behavioral_interview checks (validates the real fixture
// assertions pass against the behavioral_interview scenario loaded from disk)
// ---------------------------------------------------------------------------

import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
import { loadPack } from '@convsim/pack-loader';
import { runPackTests } from '../src/runner/index.js';

describe('golden — job-interview-basic smoke test', () => {
  const repoRoot = fileURLToPath(new URL('../../../', import.meta.url));
  const packDir = join(repoRoot, 'packs', 'official', 'job-interview-basic');

  it('passes all fixtures with the fake runtime', () => {
    const pack = loadPack(packDir, 'official');
    const result = runPackTests(pack);

    expect(result.failed).toBe(0);
    expect(result.fixture_count).toBeGreaterThan(0);
  });

  it('smoke_behavioral_interview fixture passes all static assertions', () => {
    const pack = loadPack(packDir, 'official');
    const result = runPackTests(pack);

    const fixture = result.fixtures.find((f) => f.fixture_id === 'smoke_behavioral_interview');
    expect(fixture).toBeDefined();
    expect(fixture?.status).toBe('passed');
    expect(fixture?.failures).toHaveLength(0);
    expect(fixture?.static_assertion_count).toBeGreaterThan(0);
  });

  it('reports scenario_id and turn_count in JSON output', () => {
    const pack = loadPack(packDir, 'official');
    const result = runPackTests(pack);

    const fixture = result.fixtures.find((f) => f.fixture_id === 'smoke_behavioral_interview');
    expect(fixture?.scenario_id).toBe('behavioral_interview');
    expect(fixture?.turn_count).toBe(1);
    expect(fixture?.mode).toBe('fake');
  });
});
