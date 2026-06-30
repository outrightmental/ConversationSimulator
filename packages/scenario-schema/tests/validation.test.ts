import { describe, expect, it } from 'vitest';
import {
  parseManifestYaml,
  parseNpcYaml,
  parseRubricYaml,
  parseScenarioYaml,
} from '../src/yaml-sync.js';
import {
  VALID_MANIFEST_YAML,
  VALID_NPC_YAML,
  VALID_RUBRIC_YAML,
  VALID_SCENARIO_YAML,
} from './fixtures.js';

// ---------------------------------------------------------------------------
// Manifest validation
// ---------------------------------------------------------------------------

describe('parseManifestYaml', () => {
  it('accepts a valid manifest', () => {
    const result = parseManifestYaml(VALID_MANIFEST_YAML);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.data.name).toBe('Job Interview Practice');
    expect(result.data.fictional).toBe(true);
    expect(result.data.id).toBe('job-interview-basic');
  });

  it('rejects fictional: false', () => {
    const yaml = VALID_MANIFEST_YAML.replace('fictional: true', 'fictional: false');
    const result = parseManifestYaml(yaml);
    expect(result.ok).toBe(false);
    expect(result.errors.some((e) => e.message.includes('fictional'))).toBe(true);
  });

  it('rejects missing required fields', () => {
    const result = parseManifestYaml('schema_version: "1.0"\nfictional: true\nid: test');
    expect(result.ok).toBe(false);
    const paths = result.errors.map((e) => e.path);
    expect(paths).toContain('name');
    expect(paths).toContain('version');
    expect(paths).toContain('description');
  });

  it('rejects non-semver version', () => {
    const yaml = VALID_MANIFEST_YAML.replace('version: "1.0.0"', 'version: "1.0"');
    const result = parseManifestYaml(yaml);
    expect(result.ok).toBe(false);
    expect(result.errors.some((e) => e.path === 'version')).toBe(true);
  });

  it('rejects ID with uppercase letters', () => {
    const yaml = VALID_MANIFEST_YAML.replace('\nid: job-interview-basic', '\nid: JobInterview');
    const result = parseManifestYaml(yaml);
    expect(result.ok).toBe(false);
    expect(result.errors.some((e) => e.path === 'id')).toBe(true);
  });

  it('returns YAML syntax error cleanly', () => {
    const result = parseManifestYaml(': bad: yaml:');
    expect(result.ok).toBe(false);
    expect(result.errors[0].path).toBe('(root)');
    expect(result.errors[0].message).toMatch(/YAML syntax error/);
  });

  it('preserves unknown fields in passthrough', () => {
    const yaml = VALID_MANIFEST_YAML + 'custom_field: hello\n';
    const result = parseManifestYaml(yaml);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect((result.data as Record<string, unknown>)['custom_field']).toBe('hello');
  });
});

// ---------------------------------------------------------------------------
// Scenario validation
// ---------------------------------------------------------------------------

describe('parseScenarioYaml', () => {
  it('accepts a valid scenario', () => {
    const result = parseScenarioYaml(VALID_SCENARIO_YAML);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.data.title).toBe('Behavioral Interview');
    expect(result.data.difficulty).toBe('medium');
    expect(result.data.state_defaults.trust).toBe(50);
  });

  it('rejects invalid difficulty value', () => {
    const yaml = VALID_SCENARIO_YAML.replace('difficulty: medium', 'difficulty: extreme');
    const result = parseScenarioYaml(yaml);
    expect(result.ok).toBe(false);
    expect(result.errors.some((e) => e.path === 'difficulty')).toBe(true);
  });

  it('rejects state_defaults values out of range', () => {
    const yaml = VALID_SCENARIO_YAML.replace('  trust: 50', '  trust: 150');
    const result = parseScenarioYaml(yaml);
    expect(result.ok).toBe(false);
    expect(result.errors.some((e) => e.path === 'state_defaults.trust')).toBe(true);
  });

  it('rejects duration_minutes below minimum', () => {
    const yaml = VALID_SCENARIO_YAML.replace('duration_minutes: 20', 'duration_minutes: 2');
    const result = parseScenarioYaml(yaml);
    expect(result.ok).toBe(false);
    expect(result.errors.some((e) => e.path === 'duration_minutes')).toBe(true);
  });

  it('rejects empty goals array', () => {
    const yaml = VALID_SCENARIO_YAML.replace(
      'goals:\n  - "Demonstrate relevant past experience"\n  - "Answer with the STAR method"',
      'goals: []',
    );
    const result = parseScenarioYaml(yaml);
    expect(result.ok).toBe(false);
    expect(result.errors.some((e) => e.path === 'goals')).toBe(true);
  });

  it('rejects endings with invalid condition format not blocked (passthrough)', () => {
    // Condition is a free-form string — no format restriction at schema level
    const yaml = VALID_SCENARIO_YAML.replace(
      'condition: "objective_progress >= 75"',
      'condition: "always"',
    );
    const result = parseScenarioYaml(yaml);
    expect(result.ok).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// NPC validation
// ---------------------------------------------------------------------------

describe('parseNpcYaml', () => {
  it('accepts a valid NPC', () => {
    const result = parseNpcYaml(VALID_NPC_YAML);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.data.name).toBe('Jordan Lee');
    expect(result.data.voice.tone).toBe('professional');
    expect(result.data.persona.speaking_style).toContain('Direct');
  });

  it('rejects invalid voice tone', () => {
    const yaml = VALID_NPC_YAML.replace('tone: professional', 'tone: aggressive');
    const result = parseNpcYaml(yaml);
    expect(result.ok).toBe(false);
    expect(result.errors.some((e) => e.path === 'voice.tone')).toBe(true);
  });

  it('rejects invalid voice pace', () => {
    const yaml = VALID_NPC_YAML.replace('pace: moderate', 'pace: lightning');
    const result = parseNpcYaml(yaml);
    expect(result.ok).toBe(false);
    expect(result.errors.some((e) => e.path === 'voice.pace')).toBe(true);
  });

  it('allows optional hidden_agenda to be absent', () => {
    const yaml = VALID_NPC_YAML.replace(
      /^hidden_agenda:.*$/m,
      '',
    );
    const result = parseNpcYaml(yaml);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.data.hidden_agenda).toBeUndefined();
  });

  it('rejects empty boundaries array', () => {
    const yaml = VALID_NPC_YAML.replace(
      'boundaries:\n  - "Does not ask illegal interview questions."\n  - "Will not discuss salary before a formal offer."',
      'boundaries: []',
    );
    const result = parseNpcYaml(yaml);
    expect(result.ok).toBe(false);
    expect(result.errors.some((e) => e.path === 'boundaries')).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Rubric validation
// ---------------------------------------------------------------------------

describe('parseRubricYaml', () => {
  it('accepts a valid rubric', () => {
    const result = parseRubricYaml(VALID_RUBRIC_YAML);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.data.title).toBe('Interview Performance');
    expect(result.data.dimensions).toHaveLength(2);
    expect(result.data.dimensions[0].weight).toBe(1.0);
  });

  it('rejects weight below 0.1', () => {
    const yaml = VALID_RUBRIC_YAML.replace('weight: 1.0', 'weight: 0.0');
    const result = parseRubricYaml(yaml);
    expect(result.ok).toBe(false);
    expect(result.errors.some((e) => e.path.includes('weight'))).toBe(true);
  });

  it('rejects max_score above 10', () => {
    const yaml = VALID_RUBRIC_YAML.replace('max_score: 5\n  - id:', 'max_score: 20\n  - id:');
    const result = parseRubricYaml(yaml);
    expect(result.ok).toBe(false);
    expect(result.errors.some((e) => e.path.includes('max_score'))).toBe(true);
  });

  it('rejects empty dimensions array', () => {
    const yaml = `schema_version: "1.0"\nid: test\ntitle: "Test"\ndimensions: []\n`;
    const result = parseRubricYaml(yaml);
    expect(result.ok).toBe(false);
    expect(result.errors.some((e) => e.path === 'dimensions')).toBe(true);
  });

  it('rejects dimension ID with uppercase', () => {
    const yaml = VALID_RUBRIC_YAML.replace('  - id: clarity', '  - id: Clarity');
    const result = parseRubricYaml(yaml);
    expect(result.ok).toBe(false);
    expect(result.errors.some((e) => e.path.includes('id'))).toBe(true);
  });
});
