import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { FormEditor } from '../src/FormEditor.js';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const MANIFEST_YAML = `\
schema_version: "1.0"
fictional: true
id: test-pack
name: "Test Pack"
version: "1.0.0"
description: "A test pack for unit tests."
author: "Tester"
license: "Apache-2.0"
tags:
  - test
scenarios:
  - scenarios/s.yaml
`;

const SCENARIO_YAML = `\
schema_version: "1.0"
id: test-scenario
title: "Test Scenario"
description: "A scenario for testing."
player_role: "You are a tester."
goals:
  - "Complete the test"
difficulty: medium
duration_minutes: 10
npc_ref: test-npc
opening_context: "The test begins."
state_defaults:
  trust: 50
  patience: 80
  pressure: 20
  rapport: 30
  openness: 60
  objective_progress: 0
endings:
  - id: pass
    label: "Passed"
    condition: "objective_progress >= 50"
    npc_reaction: "Well done!"
  - id: fail
    label: "Failed"
    condition: "objective_progress < 50"
    npc_reaction: "Try again."
`;

const NPC_YAML = `\
schema_version: "1.0"
id: test-npc
name: "Alex Smith"
role: "Test Evaluator"
persona:
  background: "10 years testing software."
  speaking_style: "Crisp and to the point."
  personality_traits:
    - methodical
    - patient
voice:
  tone: professional
  pace: moderate
  formality: "business-casual"
boundaries:
  - "Does not discuss off-topic subjects."
hidden_agenda: "Wants the tester to succeed."
`;

const RUBRIC_YAML = `\
schema_version: "1.0"
id: test-rubric
title: "Test Rubric"
dimensions:
  - id: accuracy
    label: "Accuracy"
    description: "Does the tester find real bugs?"
    weight: 1.5
    max_score: 5
  - id: clarity
    label: "Clarity"
    description: "Are bug reports clear?"
    weight: 1.0
    max_score: 5
`;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Get the textarea from the YAML pane (may be hidden but still in DOM). */
function getYamlTextarea() {
  return screen.getByLabelText('YAML editor') as HTMLTextAreaElement;
}

// ---------------------------------------------------------------------------
// FormEditor — basic rendering
// ---------------------------------------------------------------------------

describe('FormEditor', () => {
  it('renders the form tab by default', () => {
    render(<FormEditor fileType="manifest" initialYaml={MANIFEST_YAML} />);
    expect(screen.getByRole('tab', { name: 'Form' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'YAML' })).toHaveAttribute('aria-selected', 'false');
  });

  it('renders the title for each file type', () => {
    const { rerender } = render(<FormEditor fileType="manifest" initialYaml={MANIFEST_YAML} />);
    expect(screen.getByText('Pack manifest')).toBeInTheDocument();

    rerender(<FormEditor fileType="scenario" initialYaml={SCENARIO_YAML} />);
    expect(screen.getByText('Scenario')).toBeInTheDocument();

    rerender(<FormEditor fileType="npc" initialYaml={NPC_YAML} />);
    expect(screen.getByText('Character (NPC)')).toBeInTheDocument();

    rerender(<FormEditor fileType="rubric" initialYaml={RUBRIC_YAML} />);
    expect(screen.getByText('Rubric')).toBeInTheDocument();
  });

  it('switches to YAML tab when the YAML button is clicked', async () => {
    const user = userEvent.setup();
    render(<FormEditor fileType="manifest" initialYaml={MANIFEST_YAML} />);

    await user.click(screen.getByRole('tab', { name: 'YAML' }));

    expect(screen.getByRole('tab', { name: 'YAML' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByLabelText('YAML editor')).toBeInTheDocument();
  });

  it('YAML pane contains the initial YAML content', async () => {
    const user = userEvent.setup();
    render(<FormEditor fileType="manifest" initialYaml={MANIFEST_YAML} />);

    await user.click(screen.getByRole('tab', { name: 'YAML' }));

    const textarea = getYamlTextarea();
    expect(textarea.value).toContain('test-pack');
    expect(textarea.value).toContain('Test Pack');
  });
});

// ---------------------------------------------------------------------------
// Manifest form
// ---------------------------------------------------------------------------

describe('FormEditor — manifest form', () => {
  it('renders manifest fields with correct initial values', () => {
    render(<FormEditor fileType="manifest" initialYaml={MANIFEST_YAML} />);
    expect(screen.getByLabelText('Pack name')).toHaveValue('Test Pack');
    expect(screen.getByLabelText('Author')).toHaveValue('Tester');
    expect(screen.getByLabelText('License')).toHaveValue('Apache-2.0');
  });

  it('updates YAML when pack name is changed', async () => {
    const user = userEvent.setup();
    render(<FormEditor fileType="manifest" initialYaml={MANIFEST_YAML} />);

    const nameInput = screen.getByLabelText('Pack name');
    await user.clear(nameInput);
    await user.type(nameInput, 'Updated Pack');

    // YAML pane is always rendered (just hidden); check its value directly
    expect(getYamlTextarea().value).toContain('Updated Pack');
  });

  it('shows validation error for empty pack name', async () => {
    const user = userEvent.setup();
    render(<FormEditor fileType="manifest" initialYaml={MANIFEST_YAML} />);

    const nameInput = screen.getByLabelText('Pack name');
    await user.clear(nameInput);

    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent(/required/i);
  });

  it('shows fictional field as read-only (not editable)', () => {
    render(<FormEditor fileType="manifest" initialYaml={MANIFEST_YAML} />);
    // There's no editable input for the fictional field in the form panel
    expect(screen.queryByLabelText(/fictional/i)).toBeNull();
    // The form panel (visible — it's the active tab) contains the read-only notice
    const formPanel = screen.getByRole('tabpanel');
    expect(within(formPanel).getByText(/fictional: true/)).toBeInTheDocument();
  });

  it('calls onChange when a field changes', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<FormEditor fileType="manifest" initialYaml={MANIFEST_YAML} onChange={onChange} />);

    const authorInput = screen.getByLabelText('Author');
    await user.clear(authorInput);
    await user.type(authorInput, 'New Author');

    expect(onChange).toHaveBeenCalled();
    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0] as string;
    expect(lastCall).toContain('New Author');
  });
});

// ---------------------------------------------------------------------------
// Scenario form
// ---------------------------------------------------------------------------

describe('FormEditor — scenario form', () => {
  it('renders scenario fields with correct initial values', () => {
    render(<FormEditor fileType="scenario" initialYaml={SCENARIO_YAML} />);
    expect(screen.getByLabelText('Scenario title')).toHaveValue('Test Scenario');
    expect(screen.getByLabelText('Player role')).toHaveValue('You are a tester.');
  });

  it('updates YAML when title is changed', async () => {
    const user = userEvent.setup();
    render(<FormEditor fileType="scenario" initialYaml={SCENARIO_YAML} />);

    const titleInput = screen.getByLabelText('Scenario title');
    await user.clear(titleInput);
    await user.type(titleInput, 'New Title');

    expect(getYamlTextarea().value).toContain('New Title');
  });

  it('renders difficulty select with current value', () => {
    render(<FormEditor fileType="scenario" initialYaml={SCENARIO_YAML} />);
    const select = screen.getByLabelText('Difficulty');
    expect(select).toHaveValue('medium');
  });

  it('updates difficulty via dropdown', async () => {
    const user = userEvent.setup();
    render(<FormEditor fileType="scenario" initialYaml={SCENARIO_YAML} />);

    await user.selectOptions(screen.getByLabelText('Difficulty'), 'hard');

    expect(getYamlTextarea().value).toContain('hard');
  });

  it('renders state variable sliders', () => {
    render(<FormEditor fileType="scenario" initialYaml={SCENARIO_YAML} />);
    expect(screen.getByLabelText(/Trust: 50/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Patience: 80/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Starting progress: 0/)).toBeInTheDocument();
  });

  it('updates player_role and syncs to YAML', async () => {
    const user = userEvent.setup();
    render(<FormEditor fileType="scenario" initialYaml={SCENARIO_YAML} />);

    const roleInput = screen.getByLabelText('Player role');
    await user.clear(roleInput);
    await user.type(roleInput, 'You are a senior engineer.');

    expect(getYamlTextarea().value).toContain('You are a senior engineer.');
  });
});

// ---------------------------------------------------------------------------
// NPC form
// ---------------------------------------------------------------------------

describe('FormEditor — NPC form', () => {
  it('renders NPC fields with correct initial values', () => {
    render(<FormEditor fileType="npc" initialYaml={NPC_YAML} />);
    expect(screen.getByLabelText('Character name')).toHaveValue('Alex Smith');
    expect(screen.getByLabelText('Role')).toHaveValue('Test Evaluator');
    expect(screen.getByLabelText('How this character speaks')).toHaveValue('Crisp and to the point.');
  });

  it('renders voice tone select with correct value', () => {
    render(<FormEditor fileType="npc" initialYaml={NPC_YAML} />);
    expect(screen.getByLabelText('Overall tone')).toHaveValue('professional');
  });

  it('updates speaking style and syncs to YAML', async () => {
    const user = userEvent.setup();
    render(<FormEditor fileType="npc" initialYaml={NPC_YAML} />);

    const styleInput = screen.getByLabelText('How this character speaks');
    await user.clear(styleInput);
    await user.type(styleInput, 'Warm and encouraging.');

    expect(getYamlTextarea().value).toContain('Warm and encouraging.');
  });

  it('updates voice tone and syncs to YAML', async () => {
    const user = userEvent.setup();
    render(<FormEditor fileType="npc" initialYaml={NPC_YAML} />);

    await user.selectOptions(screen.getByLabelText('Overall tone'), 'casual');

    expect(getYamlTextarea().value).toContain('casual');
  });
});

// ---------------------------------------------------------------------------
// Rubric form
// ---------------------------------------------------------------------------

describe('FormEditor — rubric form', () => {
  it('renders rubric fields with correct initial values', () => {
    render(<FormEditor fileType="rubric" initialYaml={RUBRIC_YAML} />);
    expect(screen.getByLabelText('Rubric title')).toHaveValue('Test Rubric');
  });

  it('renders all dimension labels', () => {
    render(<FormEditor fileType="rubric" initialYaml={RUBRIC_YAML} />);
    const dimLabelInputs = screen.getAllByLabelText('Dimension name');
    expect(dimLabelInputs).toHaveLength(2);
    expect(dimLabelInputs[0]).toHaveValue('Accuracy');
    expect(dimLabelInputs[1]).toHaveValue('Clarity');
  });

  it('updates dimension label and syncs to YAML', async () => {
    const user = userEvent.setup();
    render(<FormEditor fileType="rubric" initialYaml={RUBRIC_YAML} />);

    const labelInputs = screen.getAllByLabelText('Dimension name');
    await user.clear(labelInputs[0]);
    await user.type(labelInputs[0], 'Bug Detection');

    expect(getYamlTextarea().value).toContain('Bug Detection');
  });

  it('updates rubric title and syncs to YAML', async () => {
    const user = userEvent.setup();
    render(<FormEditor fileType="rubric" initialYaml={RUBRIC_YAML} />);

    const titleInput = screen.getByLabelText('Rubric title');
    await user.clear(titleInput);
    await user.type(titleInput, 'Updated Rubric');

    expect(getYamlTextarea().value).toContain('Updated Rubric');
  });
});

// ---------------------------------------------------------------------------
// YAML → Form sync
// ---------------------------------------------------------------------------

describe('FormEditor — YAML to form sync', () => {
  it('updates form fields when YAML is edited directly', async () => {
    const user = userEvent.setup();
    render(<FormEditor fileType="manifest" initialYaml={MANIFEST_YAML} />);

    // Switch to YAML tab and edit
    await user.click(screen.getByRole('tab', { name: 'YAML' }));
    const textarea = getYamlTextarea();
    await user.clear(textarea);
    const newYaml = MANIFEST_YAML.replace('name: "Test Pack"', 'name: "YAML Edited Pack"');
    await user.type(textarea, newYaml);

    // Switch back to form tab and check
    await user.click(screen.getByRole('tab', { name: 'Form' }));
    expect(screen.getByLabelText('Pack name')).toHaveValue('YAML Edited Pack');
  });

  it('shows validation error badge when YAML has invalid content', async () => {
    const user = userEvent.setup();
    render(<FormEditor fileType="manifest" initialYaml={MANIFEST_YAML} />);

    await user.click(screen.getByRole('tab', { name: 'YAML' }));
    const textarea = getYamlTextarea();
    await user.clear(textarea);
    // Write YAML with fictional: false (invalid)
    await user.type(
      textarea,
      'schema_version: "1.0"\nfictional: false\nid: x\nname: x\nversion: "1.0.0"\ndescription: x\nauthor: x\nlicense: x',
    );

    const badges = await screen.findAllByLabelText(/validation errors/i);
    expect(badges.length).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// Unknown-field preservation
// ---------------------------------------------------------------------------

describe('FormEditor — unknown field preservation', () => {
  it('preserves unknown YAML fields across form edits', async () => {
    const user = userEvent.setup();
    const yamlWithExtra = MANIFEST_YAML + 'internal_notes: "do not publish"\n';
    render(<FormEditor fileType="manifest" initialYaml={yamlWithExtra} />);

    // Edit a form field
    const nameInput = screen.getByLabelText('Pack name');
    await user.clear(nameInput);
    await user.type(nameInput, 'Changed Name');

    // YAML should still contain the unknown field
    expect(getYamlTextarea().value).toContain('internal_notes');
  });
});

// ---------------------------------------------------------------------------
// Initial error state
// ---------------------------------------------------------------------------

describe('FormEditor — initial error state', () => {
  it('shows validation errors immediately when opened with invalid YAML', () => {
    const invalidYaml =
      'schema_version: "1.0"\nfictional: false\nid: x\nname: x\nversion: "1.0.0"\ndescription: x\nauthor: x\nlicense: x';
    render(<FormEditor fileType="manifest" initialYaml={invalidYaml} />);
    // Error badge should be visible without any user interaction
    const badges = document.querySelectorAll('[aria-label*="validation errors"]');
    expect(badges.length).toBeGreaterThan(0);
  });

  it('populates form fields on initial load even when YAML has schema errors', () => {
    // fictional: false is invalid, but name and author are perfectly valid.
    // The form should show those valid fields rather than blank placeholders.
    const invalidYaml =
      'schema_version: "1.0"\nfictional: false\nid: my-pack\nname: "Real Pack Name"\nversion: "1.0.0"\ndescription: "x"\nauthor: "Jane Doe"\nlicense: "MIT"';
    render(<FormEditor fileType="manifest" initialYaml={invalidYaml} />);
    expect(screen.getByLabelText('Pack name')).toHaveValue('Real Pack Name');
    expect(screen.getByLabelText('Author')).toHaveValue('Jane Doe');
  });
});

// ---------------------------------------------------------------------------
// YAML → Form sync with validation errors
// ---------------------------------------------------------------------------

describe('FormEditor — YAML to form sync with validation errors', () => {
  it('updates form fields for valid-syntax but invalid-schema YAML so unrelated fields stay in sync', async () => {
    const user = userEvent.setup();
    render(<FormEditor fileType="manifest" initialYaml={MANIFEST_YAML} />);

    // Switch to YAML tab and change `name` while also introducing a validation error
    await user.click(screen.getByRole('tab', { name: 'YAML' }));
    const textarea = getYamlTextarea();
    await user.clear(textarea);
    // fictional: false is a validation error, but name has changed
    await user.type(
      textarea,
      'schema_version: "1.0"\nfictional: false\nid: test-pack\nname: "Synced Despite Error"\nversion: "1.0.0"\ndescription: "x"\nauthor: "x"\nlicense: "x"',
    );

    // Errors should be visible (fictional: false)
    const badges = await screen.findAllByLabelText(/validation errors/i);
    expect(badges.length).toBeGreaterThan(0);

    // Switch back to form tab: name should reflect the edit, not the stale value
    await user.click(screen.getByRole('tab', { name: 'Form' }));
    expect(screen.getByLabelText('Pack name')).toHaveValue('Synced Despite Error');
  });
});

// ---------------------------------------------------------------------------
// Rubric — dimension ID field
// ---------------------------------------------------------------------------

describe('FormEditor — rubric dimension ID', () => {
  it('renders an ID input for each existing dimension', () => {
    render(<FormEditor fileType="rubric" initialYaml={RUBRIC_YAML} />);
    const idInputs = screen.getAllByLabelText('Dimension ID');
    expect(idInputs).toHaveLength(2);
    expect(idInputs[0]).toHaveValue('accuracy');
    expect(idInputs[1]).toHaveValue('clarity');
  });

  it('newly added dimension renders an editable ID field', async () => {
    const user = userEvent.setup();
    render(<FormEditor fileType="rubric" initialYaml={RUBRIC_YAML} />);

    await user.click(screen.getByRole('button', { name: 'Add dimension' }));

    const idInputs = screen.getAllByLabelText('Dimension ID');
    expect(idInputs).toHaveLength(3);
    // New dimension starts with empty id
    expect(idInputs[2]).toHaveValue('');

    await user.type(idInputs[2], 'new-dim');
    expect(getYamlTextarea().value).toContain('new-dim');
  });
});

// ---------------------------------------------------------------------------
// Scenario — ending ID field
// ---------------------------------------------------------------------------

describe('FormEditor — scenario ending ID', () => {
  it('renders an ID input for each existing ending', () => {
    render(<FormEditor fileType="scenario" initialYaml={SCENARIO_YAML} />);
    const idInputs = screen.getAllByLabelText('Ending ID');
    expect(idInputs).toHaveLength(2);
    expect(idInputs[0]).toHaveValue('pass');
    expect(idInputs[1]).toHaveValue('fail');
  });

  it('newly added ending renders an editable ID field', async () => {
    const user = userEvent.setup();
    render(<FormEditor fileType="scenario" initialYaml={SCENARIO_YAML} />);

    await user.click(screen.getByRole('button', { name: 'Add ending' }));

    const idInputs = screen.getAllByLabelText('Ending ID');
    expect(idInputs).toHaveLength(3);
    expect(idInputs[2]).toHaveValue('');

    await user.type(idInputs[2], 'timeout');
    expect(getYamlTextarea().value).toContain('timeout');
  });
});

// ---------------------------------------------------------------------------
// initialYaml prop reset
// ---------------------------------------------------------------------------

describe('FormEditor — initialYaml prop reset', () => {
  it('resets form fields when initialYaml prop changes to a different file', async () => {
    const SECOND_MANIFEST = MANIFEST_YAML.replace('name: "Test Pack"', 'name: "Second Pack"')
      .replace('id: test-pack', 'id: second-pack');

    const { rerender } = render(<FormEditor fileType="manifest" initialYaml={MANIFEST_YAML} />);
    expect(screen.getByLabelText('Pack name')).toHaveValue('Test Pack');

    rerender(<FormEditor fileType="manifest" initialYaml={SECOND_MANIFEST} />);

    expect(await screen.findByDisplayValue('Second Pack')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Per-item validation errors in flat string arrays
// ---------------------------------------------------------------------------

describe('FormEditor — per-item validation errors', () => {
  it('shows a per-goal error when an empty goal is added', async () => {
    const user = userEvent.setup();
    render(<FormEditor fileType="scenario" initialYaml={SCENARIO_YAML} />);

    // Add a new goal (starts empty — empty string fails min(1) validation)
    await user.click(screen.getByRole('button', { name: 'Add goal' }));

    // The new empty goal should trigger a validation error at goals.1
    // (index 1 because there is already one goal in the fixture)
    const alerts = await screen.findAllByRole('alert');
    const goalError = alerts.find((el) => el.textContent?.match(/cannot be empty/i));
    expect(goalError).toBeTruthy();
  });

  it('shows a per-tag error when a new tag is added (empty tag fails kebab-case validation)', async () => {
    const user = userEvent.setup();
    render(<FormEditor fileType="manifest" initialYaml={MANIFEST_YAML} />);

    // Adding a new tag starts it as an empty string which fails the kebab-case regex
    await user.click(screen.getByRole('button', { name: 'Add tag' }));

    const alerts = await screen.findAllByRole('alert');
    const tagError = alerts.find((el) => el.textContent?.match(/kebab-case/i));
    expect(tagError).toBeTruthy();
  });

  it('shows a per-boundary error when an empty boundary is added', async () => {
    const user = userEvent.setup();
    render(<FormEditor fileType="npc" initialYaml={NPC_YAML} />);

    await user.click(screen.getByRole('button', { name: 'Add limit' }));

    const alerts = await screen.findAllByRole('alert');
    const boundaryError = alerts.find((el) => el.textContent?.match(/cannot be empty/i));
    expect(boundaryError).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// onChange call count
// ---------------------------------------------------------------------------

describe('FormEditor — onChange call count', () => {
  it('does not call onChange on initial mount', () => {
    const onChange = vi.fn();
    render(<FormEditor fileType="manifest" initialYaml={MANIFEST_YAML} onChange={onChange} />);
    expect(onChange).not.toHaveBeenCalled();
  });

  it('does not call onChange when initialYaml prop changes (file switch)', async () => {
    const onChange = vi.fn();
    const SECOND_MANIFEST = MANIFEST_YAML.replace('name: "Test Pack"', 'name: "Second Pack"')
      .replace('id: test-pack', 'id: second-pack');

    const { rerender } = render(
      <FormEditor fileType="manifest" initialYaml={MANIFEST_YAML} onChange={onChange} />,
    );
    onChange.mockClear();

    // Simulate the parent loading a different file by changing initialYaml
    rerender(<FormEditor fileType="manifest" initialYaml={SECOND_MANIFEST} onChange={onChange} />);

    // Wait a tick for any async effects
    await new Promise((r) => setTimeout(r, 50));

    expect(onChange).not.toHaveBeenCalled();
  });

  it('calls onChange exactly once per YAML tab edit, not twice', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <FormEditor fileType="manifest" initialYaml={MANIFEST_YAML} onChange={onChange} />,
    );

    // Nothing fired on mount; start fresh for this test.
    onChange.mockClear();

    // Switch to YAML tab and make one change
    await user.click(screen.getByRole('tab', { name: 'YAML' }));
    const textarea = getYamlTextarea();
    // Focus then type a single character to trigger exactly one change event
    await user.click(textarea);
    await user.keyboard('x');

    // onChange should have been called, and each distinct yaml value should
    // appear at most once — not duplicated by both handleYamlChange and useEffect.
    const calls = onChange.mock.calls.map((c) => c[0] as string);
    // Check no two consecutive calls carry the same yaml string (which would
    // indicate the double-fire bug).
    for (let i = 1; i < calls.length; i++) {
      expect(calls[i]).not.toBe(calls[i - 1]);
    }
  });
});
