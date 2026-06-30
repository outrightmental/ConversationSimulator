import { describe, expect, it } from 'vitest';
import {
  getByPath,
  mergeManifestToYaml,
  mergeNpcToYaml,
  mergeRubricToYaml,
  mergeScenarioToYaml,
  mergeToYaml,
  parseByType,
  parseManifestYaml,
  parseNpcYaml,
  parseRubricYaml,
  parseScenarioYaml,
  setByPath,
} from '../src/yaml-sync.js';
import {
  VALID_MANIFEST_YAML,
  VALID_NPC_YAML,
  VALID_RUBRIC_YAML,
  VALID_SCENARIO_YAML,
} from './fixtures.js';

// ---------------------------------------------------------------------------
// setByPath / getByPath
// ---------------------------------------------------------------------------

describe('setByPath', () => {
  it('sets a top-level field', () => {
    const obj = { a: 1, b: 2 };
    const result = setByPath(obj, 'a', 99);
    expect(result).toEqual({ a: 99, b: 2 });
    expect(obj.a).toBe(1); // original unchanged
  });

  it('sets a nested field', () => {
    const obj = { persona: { speaking_style: 'old', background: 'bg' } };
    const result = setByPath(obj, 'persona.speaking_style', 'new style');
    expect((result.persona as Record<string, unknown>)['speaking_style']).toBe('new style');
    expect((result.persona as Record<string, unknown>)['background']).toBe('bg');
  });

  it('creates missing intermediate objects', () => {
    const obj: Record<string, unknown> = {};
    const result = setByPath(obj, 'state_defaults.trust', 75);
    expect((result.state_defaults as Record<string, unknown>)['trust']).toBe(75);
  });
});

describe('getByPath', () => {
  it('reads a top-level field', () => {
    expect(getByPath({ name: 'Alice' }, 'name')).toBe('Alice');
  });

  it('reads a nested field', () => {
    expect(getByPath({ voice: { tone: 'formal' } }, 'voice.tone')).toBe('formal');
  });

  it('returns undefined for missing paths', () => {
    expect(getByPath({}, 'a.b.c')).toBeUndefined();
  });

  it('reads an array element by numeric index', () => {
    expect(getByPath({ goals: ['first', 'second'] }, 'goals.0')).toBe('first');
    expect(getByPath({ goals: ['first', 'second'] }, 'goals.1')).toBe('second');
  });

  it('reads a field inside an array element', () => {
    const obj = { endings: [{ id: 'offer', label: 'Offer Extended' }] };
    expect(getByPath(obj as Record<string, unknown>, 'endings.0.label')).toBe('Offer Extended');
  });

  it('returns undefined for out-of-bounds array index', () => {
    expect(getByPath({ goals: ['a'] }, 'goals.5')).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Manifest round-trip
// ---------------------------------------------------------------------------

describe('mergeManifestToYaml', () => {
  it('round-trips without modification', () => {
    const result = parseManifestYaml(VALID_MANIFEST_YAML);
    expect(result.ok).toBe(true);
    if (!result.ok) return;

    const newYaml = mergeManifestToYaml(result.data, VALID_MANIFEST_YAML);
    const re = parseManifestYaml(newYaml);
    expect(re.ok).toBe(true);
    if (!re.ok) return;
    expect(re.data.name).toBe(result.data.name);
    expect(re.data.id).toBe(result.data.id);
  });

  it('updates a single field while preserving others', () => {
    const newYaml = mergeManifestToYaml({ name: 'Updated Name' }, VALID_MANIFEST_YAML);
    const result = parseManifestYaml(newYaml);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.data.name).toBe('Updated Name');
    expect(result.data.id).toBe('job-interview-basic');
    expect(result.data.author).toBe('Conversation Simulator Contributors');
  });

  it('preserves unknown fields from original YAML', () => {
    const withExtra = VALID_MANIFEST_YAML + 'custom_metadata:\n  internal_id: 42\n';
    const newYaml = mergeManifestToYaml({ name: 'Changed' }, withExtra);
    expect(newYaml).toContain('custom_metadata');
    expect(newYaml).toContain('internal_id');
  });

  it('handles empty original YAML gracefully', () => {
    const newYaml = mergeManifestToYaml(
      { schema_version: '1.0', fictional: true, id: 'new-pack', name: 'New' },
      '',
    );
    expect(newYaml).toContain('new-pack');
    expect(newYaml).toContain('New');
  });
});

// ---------------------------------------------------------------------------
// Scenario round-trip
// ---------------------------------------------------------------------------

describe('mergeScenarioToYaml', () => {
  it('round-trips a full scenario', () => {
    const parsed = parseScenarioYaml(VALID_SCENARIO_YAML);
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;

    const newYaml = mergeScenarioToYaml(parsed.data, VALID_SCENARIO_YAML);
    const reparsed = parseScenarioYaml(newYaml);
    expect(reparsed.ok).toBe(true);
    if (!reparsed.ok) return;
    expect(reparsed.data.title).toBe(parsed.data.title);
    expect(reparsed.data.state_defaults).toEqual(parsed.data.state_defaults);
    expect(reparsed.data.endings).toHaveLength(parsed.data.endings.length);
  });

  it('updates title and preserves state_defaults', () => {
    const newYaml = mergeScenarioToYaml({ title: 'New Title' }, VALID_SCENARIO_YAML);
    const result = parseScenarioYaml(newYaml);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.data.title).toBe('New Title');
    expect(result.data.state_defaults.trust).toBe(50);
  });

  it('updates a state_defaults value correctly', () => {
    const newYaml = mergeScenarioToYaml(
      { state_defaults: { trust: 75, patience: 80, pressure: 20, rapport: 30, openness: 60, objective_progress: 0 } },
      VALID_SCENARIO_YAML,
    );
    const result = parseScenarioYaml(newYaml);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.data.state_defaults.trust).toBe(75);
  });

  it('updates player_role', () => {
    const newRole = 'You are applying for a senior engineer role.';
    const newYaml = mergeScenarioToYaml({ player_role: newRole }, VALID_SCENARIO_YAML);
    const result = parseScenarioYaml(newYaml);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.data.player_role).toBe(newRole);
  });

  it('updates difficulty', () => {
    const newYaml = mergeScenarioToYaml({ difficulty: 'hard' }, VALID_SCENARIO_YAML);
    const result = parseScenarioYaml(newYaml);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.data.difficulty).toBe('hard');
  });

  it('preserves unknown fields inside ending objects', () => {
    const yamlWithExtra = VALID_SCENARIO_YAML.replace(
      '    npc_reaction: "I was genuinely impressed. We would like to move you forward."',
      '    npc_reaction: "I was genuinely impressed. We would like to move you forward."\n    custom_tag: "success-path"',
    );
    const parsed = parseScenarioYaml(yamlWithExtra);
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    expect((parsed.data.endings[0] as Record<string, unknown>)['custom_tag']).toBe('success-path');

    const newYaml = mergeScenarioToYaml({ title: 'New Title' }, yamlWithExtra);
    expect(newYaml).toContain('custom_tag');
    expect(newYaml).toContain('success-path');
  });
});

// ---------------------------------------------------------------------------
// NPC round-trip
// ---------------------------------------------------------------------------

describe('mergeNpcToYaml', () => {
  it('round-trips a full NPC', () => {
    const parsed = parseNpcYaml(VALID_NPC_YAML);
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;

    const newYaml = mergeNpcToYaml(parsed.data, VALID_NPC_YAML);
    const reparsed = parseNpcYaml(newYaml);
    expect(reparsed.ok).toBe(true);
    if (!reparsed.ok) return;
    expect(reparsed.data.name).toBe(parsed.data.name);
    expect(reparsed.data.persona.speaking_style).toBe(parsed.data.persona.speaking_style);
  });

  it('updates speaking_style while preserving boundaries', () => {
    const newStyle = 'Warm but assertive. Asks probing follow-up questions.';
    const newYaml = mergeNpcToYaml(
      { persona: { speaking_style: newStyle, background: '10 years', personality_traits: ['analytical'] } },
      VALID_NPC_YAML,
    );
    const result = parseNpcYaml(newYaml);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.data.persona.speaking_style).toBe(newStyle);
    expect(result.data.boundaries.length).toBeGreaterThan(0);
  });

  it('updates voice.tone', () => {
    const newYaml = mergeNpcToYaml(
      { voice: { tone: 'casual', pace: 'moderate', formality: 'relaxed' } },
      VALID_NPC_YAML,
    );
    const result = parseNpcYaml(newYaml);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.data.voice.tone).toBe('casual');
  });
});

// ---------------------------------------------------------------------------
// Rubric round-trip
// ---------------------------------------------------------------------------

describe('mergeRubricToYaml', () => {
  it('round-trips a full rubric', () => {
    const parsed = parseRubricYaml(VALID_RUBRIC_YAML);
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;

    const newYaml = mergeRubricToYaml(parsed.data, VALID_RUBRIC_YAML);
    const reparsed = parseRubricYaml(newYaml);
    expect(reparsed.ok).toBe(true);
    if (!reparsed.ok) return;
    expect(reparsed.data.dimensions).toHaveLength(parsed.data.dimensions.length);
    expect(reparsed.data.dimensions[0].label).toBe(parsed.data.dimensions[0].label);
  });

  it('updates rubric title', () => {
    const newYaml = mergeRubricToYaml({ title: 'Updated Rubric' }, VALID_RUBRIC_YAML);
    const result = parseRubricYaml(newYaml);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.data.title).toBe('Updated Rubric');
    expect(result.data.dimensions).toHaveLength(2);
  });

  it('preserves unknown fields inside dimension objects', () => {
    const yamlWithExtra = VALID_RUBRIC_YAML.replace(
      '    weight: 1.0',
      '    weight: 1.0\n    reviewer_note: "internal use only"',
    );
    const parsed = parseRubricYaml(yamlWithExtra);
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    expect((parsed.data.dimensions[0] as Record<string, unknown>)['reviewer_note']).toBe(
      'internal use only',
    );

    const newYaml = mergeRubricToYaml({ title: 'Changed Title' }, yamlWithExtra);
    expect(newYaml).toContain('reviewer_note');
    expect(newYaml).toContain('internal use only');
  });
});

// ---------------------------------------------------------------------------
// Generic dispatch
// ---------------------------------------------------------------------------

describe('parseByType', () => {
  it('dispatches manifest correctly', () => {
    const result = parseByType('manifest', VALID_MANIFEST_YAML);
    expect(result.ok).toBe(true);
  });

  it('dispatches scenario correctly', () => {
    const result = parseByType('scenario', VALID_SCENARIO_YAML);
    expect(result.ok).toBe(true);
  });

  it('dispatches npc correctly', () => {
    const result = parseByType('npc', VALID_NPC_YAML);
    expect(result.ok).toBe(true);
  });

  it('dispatches rubric correctly', () => {
    const result = parseByType('rubric', VALID_RUBRIC_YAML);
    expect(result.ok).toBe(true);
  });
});

describe('mergeToYaml', () => {
  it('merges manifest via dispatch', () => {
    const yaml = mergeToYaml('manifest', { name: 'New Name' }, VALID_MANIFEST_YAML);
    expect(yaml).toContain('New Name');
  });

  it('merges scenario via dispatch', () => {
    const yaml = mergeToYaml('scenario', { title: 'New Title' }, VALID_SCENARIO_YAML);
    expect(yaml).toContain('New Title');
  });

  it('merges npc via dispatch', () => {
    const yaml = mergeToYaml('npc', { name: 'Sam Park' }, VALID_NPC_YAML);
    expect(yaml).toContain('Sam Park');
  });

  it('merges rubric via dispatch', () => {
    const yaml = mergeToYaml('rubric', { title: 'New Rubric' }, VALID_RUBRIC_YAML);
    expect(yaml).toContain('New Rubric');
  });
});
