import React from 'react';
import type { FieldError } from '@convsim/scenario-schema';
import { FieldWrapper, errorFor, str, num } from './shared.js';

interface ScenarioFormProps {
  values: Record<string, unknown>;
  errors: FieldError[];
  onChange: (path: string, value: unknown) => void;
}

const STATE_VARS: Array<{ key: string; label: string; hint: string }> = [
  { key: 'trust', label: 'Trust', hint: "How much the NPC trusts the player at the start (0 = none, 100 = complete)." },
  { key: 'patience', label: 'Patience', hint: "How patient the NPC is at the start." },
  { key: 'pressure', label: 'Pressure', hint: "How much situational pressure the NPC feels." },
  { key: 'rapport', label: 'Rapport', hint: "Level of positive connection between NPC and player." },
  { key: 'openness', label: 'Openness', hint: "How open the NPC is to the player's ideas." },
  {
    key: 'objective_progress',
    label: 'Starting progress',
    hint: 'How much of the player goal is already achieved. Usually 0.',
  },
];

function StateSlider({
  uid,
  varKey,
  label,
  hint,
  value,
  error,
  onChange,
}: {
  uid: string;
  varKey: string;
  label: string;
  hint: string;
  value: number;
  error?: string;
  onChange: (v: number) => void;
}) {
  const id = `${uid}-state-${varKey}`;
  return (
    <div className="form-field" data-invalid={!!error}>
      <label htmlFor={id} className="form-field__label">
        {label}: <strong>{value}</strong>
      </label>
      <p className="form-field__hint">{hint}</p>
      <input
        id={id}
        type="range"
        min={0}
        max={100}
        step={5}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={value}
      />
      {error && (
        <p className="form-field__error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

/**
 * Form panel for editing a scenario YAML file's common fields.
 *
 * Covers: title, description, player role, goals, difficulty, duration,
 * opening context, starting state variables, and endings.
 */
export function ScenarioForm({ values, errors, onChange }: ScenarioFormProps) {
  const uid = React.useId();
  const goals = Array.isArray(values['goals']) ? (values['goals'] as string[]) : [];
  const stateDefaults =
    values['state_defaults'] && typeof values['state_defaults'] === 'object'
      ? (values['state_defaults'] as Record<string, unknown>)
      : {};
  const endings = Array.isArray(values['endings'])
    ? (values['endings'] as Array<Record<string, unknown>>)
    : [];

  function handleGoalAdd() {
    onChange('goals', [...goals, '']);
  }
  function handleGoalChange(i: number, v: string) {
    onChange('goals', goals.map((g, idx) => (idx === i ? v : g)));
  }
  function handleGoalRemove(i: number) {
    onChange('goals', goals.filter((_, idx) => idx !== i));
  }

  function handleEndingChange(i: number, field: string, v: string) {
    const updated = endings.map((e, idx) => (idx === i ? { ...e, [field]: v } : e));
    onChange('endings', updated);
  }
  function handleEndingAdd() {
    onChange('endings', [...endings, { id: '', label: '', condition: '', npc_reaction: '' }]);
  }
  function handleEndingRemove(i: number) {
    onChange('endings', endings.filter((_, idx) => idx !== i));
  }

  return (
    <div className="scenario-form" role="form" aria-label="Scenario editor">
      <FieldWrapper
        id={`${uid}-scenario-title`}
        label="Scenario title"
        hint='Shown in the scenario list (e.g. "Behavioral Interview").'
        error={errorFor(errors, 'title')}
      >
        <input
          id={`${uid}-scenario-title`}
          type="text"
          className="form-field__input"
          value={str(values['title'])}
          onChange={(e) => onChange('title', e.target.value)}
          maxLength={120}
          placeholder="My Scenario"
        />
      </FieldWrapper>

      <FieldWrapper
        id={`${uid}-scenario-description`}
        label="Description"
        hint="Short summary shown before the player starts."
        error={errorFor(errors, 'description')}
      >
        <textarea
          id={`${uid}-scenario-description`}
          className="form-field__textarea"
          value={str(values['description'])}
          onChange={(e) => onChange('description', e.target.value)}
          rows={3}
          maxLength={1000}
        />
      </FieldWrapper>

      <FieldWrapper
        id={`${uid}-scenario-player-role`}
        label="Player role"
        hint='Tells the player who they are in this scenario (e.g. "You are interviewing for a software engineering position").'
        error={errorFor(errors, 'player_role')}
      >
        <textarea
          id={`${uid}-scenario-player-role`}
          className="form-field__textarea"
          value={str(values['player_role'])}
          onChange={(e) => onChange('player_role', e.target.value)}
          rows={2}
          maxLength={500}
        />
      </FieldWrapper>

      <fieldset className="form-fieldset">
        <legend className="form-fieldset__legend">Goals</legend>
        <p className="form-field__hint">
          What the player is trying to accomplish. Shown during the conversation.
        </p>
        {errorFor(errors, 'goals') && (
          <p className="form-field__error" role="alert">
            {errorFor(errors, 'goals')}
          </p>
        )}
        <ul className="form-list" aria-label="Goal list">
          {goals.map((goal, i) => (
            <li key={i} className="form-list__item">
              <input
                type="text"
                className="form-field__input form-list__item-input"
                value={str(goal)}
                onChange={(e) => handleGoalChange(i, e.target.value)}
                placeholder="Demonstrate relevant experience"
                aria-label={`Goal ${i + 1}`}
                maxLength={200}
              />
              <button
                type="button"
                className="form-list__remove-btn"
                onClick={() => handleGoalRemove(i)}
                aria-label={`Remove goal ${i + 1}`}
              >
                Remove
              </button>
              {errorFor(errors, `goals.${i}`) && (
                <p className="form-field__error" role="alert">
                  {errorFor(errors, `goals.${i}`)}
                </p>
              )}
            </li>
          ))}
        </ul>
        <button type="button" className="form-list__add-btn" onClick={handleGoalAdd}>
          Add goal
        </button>
      </fieldset>

      <FieldWrapper
        id={`${uid}-scenario-difficulty`}
        label="Difficulty"
        hint="Controls how challenging the NPC will be during the conversation."
        error={errorFor(errors, 'difficulty')}
      >
        <select
          id={`${uid}-scenario-difficulty`}
          className="form-field__select"
          value={str(values['difficulty'])}
          onChange={(e) => onChange('difficulty', e.target.value)}
        >
          <option value="">— choose —</option>
          <option value="warm">Warm — forgiving, patient NPC</option>
          <option value="standard">Standard — balanced challenge</option>
          <option value="hard">Hard — demanding, pushes back</option>
          <option value="adversarial">Adversarial — highly skeptical NPC</option>
        </select>
      </FieldWrapper>

      <FieldWrapper
        id={`${uid}-scenario-duration`}
        label="Suggested duration (minutes)"
        hint="Approximate play time shown to players. Between 5 and 120 minutes."
        error={errorFor(errors, 'duration_minutes')}
      >
        <input
          id={`${uid}-scenario-duration`}
          type="number"
          className="form-field__input form-field__input--short"
          value={num(values['duration_minutes'], 20)}
          min={5}
          max={120}
          onChange={(e) => onChange('duration_minutes', Number(e.target.value))}
        />
      </FieldWrapper>

      <FieldWrapper
        id={`${uid}-scenario-opening`}
        label="Opening context"
        hint="Scene-setting text shown to the player just before the first NPC turn."
        error={errorFor(errors, 'opening_context')}
      >
        <textarea
          id={`${uid}-scenario-opening`}
          className="form-field__textarea"
          value={str(values['opening_context'])}
          onChange={(e) => onChange('opening_context', e.target.value)}
          rows={3}
          maxLength={1000}
        />
      </FieldWrapper>

      <fieldset className="form-fieldset">
        <legend className="form-fieldset__legend">Starting conversation state</legend>
        <p className="form-field__hint">
          These values (0–100) set where the NPC begins emotionally. They shift during the
          conversation based on how the player responds.
        </p>
        {STATE_VARS.map(({ key, label, hint }) => (
          <StateSlider
            key={key}
            uid={uid}
            varKey={key}
            label={label}
            hint={hint}
            value={num(stateDefaults[key], 50)}
            error={errorFor(errors, `state_defaults.${key}`)}
            onChange={(v) => {
              const updated = { ...stateDefaults, [key]: v };
              onChange('state_defaults', updated);
            }}
          />
        ))}
      </fieldset>

      <fieldset className="form-fieldset">
        <legend className="form-fieldset__legend">Endings</legend>
        <p className="form-field__hint">
          Define what happens when the session ends. Conditions reference state variable names
          (e.g. <code>objective_progress &gt;= 75</code>).
        </p>
        {errorFor(errors, 'endings') && (
          <p className="form-field__error" role="alert">
            {errorFor(errors, 'endings')}
          </p>
        )}
        {endings.map((ending, i) => (
          <div key={i} className="form-card">
            <div className="form-card__header">
              <span className="form-card__title">Ending {i + 1}</span>
              <button
                type="button"
                className="form-list__remove-btn"
                onClick={() => handleEndingRemove(i)}
                aria-label={`Remove ending ${i + 1}`}
              >
                Remove
              </button>
            </div>
            <FieldWrapper
              id={`${uid}-ending-${i}-id`}
              label="Ending ID"
              hint='Internal kebab-case or snake_case identifier (e.g. "offer-extended").'
              error={errorFor(errors, `endings.${i}.id`)}
            >
              <input
                id={`${uid}-ending-${i}-id`}
                type="text"
                className="form-field__input"
                value={str(ending['id'])}
                onChange={(e) => handleEndingChange(i, 'id', e.target.value)}
                maxLength={32}
                placeholder="offer-extended"
                pattern="[a-z][a-z0-9_-]*"
              />
            </FieldWrapper>
            <FieldWrapper
              id={`${uid}-ending-${i}-label`}
              label="Label"
              hint='Shown on the debrief screen (e.g. "Offer Extended").'
              error={errorFor(errors, `endings.${i}.label`)}
            >
              <input
                id={`${uid}-ending-${i}-label`}
                type="text"
                className="form-field__input"
                value={str(ending['label'])}
                onChange={(e) => handleEndingChange(i, 'label', e.target.value)}
                maxLength={60}
              />
            </FieldWrapper>
            <FieldWrapper
              id={`${uid}-ending-${i}-condition`}
              label="Condition"
              hint='Expression evaluated at session end (e.g. objective_progress >= 75).'
              error={errorFor(errors, `endings.${i}.condition`)}
            >
              <input
                id={`${uid}-ending-${i}-condition`}
                type="text"
                className="form-field__input"
                value={str(ending['condition'])}
                onChange={(e) => handleEndingChange(i, 'condition', e.target.value)}
                placeholder="objective_progress >= 75"
              />
            </FieldWrapper>
            <FieldWrapper
              id={`${uid}-ending-${i}-reaction`}
              label="NPC reaction"
              hint="What the NPC says when this ending triggers."
              error={errorFor(errors, `endings.${i}.npc_reaction`)}
            >
              <textarea
                id={`${uid}-ending-${i}-reaction`}
                className="form-field__textarea"
                value={str(ending['npc_reaction'])}
                onChange={(e) => handleEndingChange(i, 'npc_reaction', e.target.value)}
                rows={2}
                maxLength={500}
              />
            </FieldWrapper>
          </div>
        ))}
        <button type="button" className="form-list__add-btn" onClick={handleEndingAdd}>
          Add ending
        </button>
      </fieldset>
    </div>
  );
}
