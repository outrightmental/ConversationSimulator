import React from 'react';
import type { FieldError } from '@convsim/scenario-schema';

interface NpcFormProps {
  values: Record<string, unknown>;
  errors: FieldError[];
  onChange: (path: string, value: unknown) => void;
}

function str(v: unknown): string {
  return typeof v === 'string' ? v : '';
}

function FieldWrapper({
  id,
  label,
  hint,
  error,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="form-field" data-invalid={!!error}>
      <label htmlFor={id} className="form-field__label">
        {label}
      </label>
      {hint && <p className="form-field__hint">{hint}</p>}
      {children}
      {error && (
        <p className="form-field__error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

function errorFor(errors: FieldError[], path: string): string | undefined {
  return errors.find((e) => e.path === path)?.message;
}

/**
 * Form panel for editing an NPC definition YAML file.
 *
 * Covers: name, role, persona (background, speaking style, personality traits),
 * voice (tone, pace, formality), boundaries, and hidden agenda.
 */
export function NpcForm({ values, errors, onChange }: NpcFormProps) {
  const persona =
    values['persona'] && typeof values['persona'] === 'object'
      ? (values['persona'] as Record<string, unknown>)
      : {};
  const voice =
    values['voice'] && typeof values['voice'] === 'object'
      ? (values['voice'] as Record<string, unknown>)
      : {};
  const boundaries = Array.isArray(values['boundaries'])
    ? (values['boundaries'] as string[])
    : [];
  const traits = Array.isArray(persona['personality_traits'])
    ? (persona['personality_traits'] as string[])
    : [];

  function handlePersonaChange(field: string, value: unknown) {
    onChange('persona', { ...persona, [field]: value });
  }
  function handleVoiceChange(field: string, value: unknown) {
    onChange('voice', { ...voice, [field]: value });
  }

  function handleTraitAdd() {
    handlePersonaChange('personality_traits', [...traits, '']);
  }
  function handleTraitChange(i: number, v: string) {
    handlePersonaChange(
      'personality_traits',
      traits.map((t, idx) => (idx === i ? v : t)),
    );
  }
  function handleTraitRemove(i: number) {
    handlePersonaChange('personality_traits', traits.filter((_, idx) => idx !== i));
  }

  function handleBoundaryAdd() {
    onChange('boundaries', [...boundaries, '']);
  }
  function handleBoundaryChange(i: number, v: string) {
    onChange('boundaries', boundaries.map((b, idx) => (idx === i ? v : b)));
  }
  function handleBoundaryRemove(i: number) {
    onChange('boundaries', boundaries.filter((_, idx) => idx !== i));
  }

  return (
    <div className="npc-form" role="form" aria-label="NPC editor">
      <FieldWrapper
        id="npc-name"
        label="Character name"
        hint="The name shown to players during the conversation."
        error={errorFor(errors, 'name')}
      >
        <input
          id="npc-name"
          type="text"
          className="form-field__input"
          value={str(values['name'])}
          onChange={(e) => onChange('name', e.target.value)}
          maxLength={80}
          placeholder="Jordan Lee"
        />
      </FieldWrapper>

      <FieldWrapper
        id="npc-role"
        label="Role"
        hint='The character occupational role in the scenario context (e.g. "Senior Engineering Manager").'
        error={errorFor(errors, 'role')}
      >
        <input
          id="npc-role"
          type="text"
          className="form-field__input"
          value={str(values['role'])}
          onChange={(e) => onChange('role', e.target.value)}
          maxLength={200}
          placeholder="Senior Engineering Manager"
        />
      </FieldWrapper>

      <fieldset className="form-fieldset">
        <legend className="form-fieldset__legend">Persona</legend>

        <FieldWrapper
          id="npc-background"
          label="Background"
          hint="Brief backstory provided to the AI model — not shown directly to the player."
          error={errorFor(errors, 'persona.background')}
        >
          <textarea
            id="npc-background"
            className="form-field__textarea"
            value={str(persona['background'])}
            onChange={(e) => handlePersonaChange('background', e.target.value)}
            rows={3}
            maxLength={1000}
            placeholder="10 years of software engineering experience..."
          />
        </FieldWrapper>

        <FieldWrapper
          id="npc-speaking-style"
          label="How this character speaks"
          hint="Describe their tone, vocabulary, and communication habits. This directly shapes every NPC response."
          error={errorFor(errors, 'persona.speaking_style')}
        >
          <textarea
            id="npc-speaking-style"
            className="form-field__textarea"
            value={str(persona['speaking_style'])}
            onChange={(e) => handlePersonaChange('speaking_style', e.target.value)}
            rows={3}
            maxLength={500}
            placeholder="Direct and concise. Uses technical vocabulary. Asks follow-up questions when answers are vague."
          />
        </FieldWrapper>

        <fieldset className="form-fieldset">
          <legend className="form-fieldset__legend">Personality traits</legend>
          <p className="form-field__hint">
            Short descriptors that shape this character's behaviour (e.g. analytical, empathetic).
          </p>
          {errorFor(errors, 'persona.personality_traits') && (
            <p className="form-field__error" role="alert">
              {errorFor(errors, 'persona.personality_traits')}
            </p>
          )}
          <ul className="form-list" aria-label="Personality trait list">
            {traits.map((trait, i) => (
              <li key={i} className="form-list__item">
                <input
                  type="text"
                  className="form-field__input form-list__item-input"
                  value={str(trait)}
                  onChange={(e) => handleTraitChange(i, e.target.value)}
                  placeholder="analytical"
                  aria-label={`Trait ${i + 1}`}
                  maxLength={50}
                />
                <button
                  type="button"
                  className="form-list__remove-btn"
                  onClick={() => handleTraitRemove(i)}
                  aria-label={`Remove trait ${i + 1}`}
                >
                  Remove
                </button>
                {errorFor(errors, `persona.personality_traits.${i}`) && (
                  <p className="form-field__error" role="alert">
                    {errorFor(errors, `persona.personality_traits.${i}`)}
                  </p>
                )}
              </li>
            ))}
          </ul>
          <button type="button" className="form-list__add-btn" onClick={handleTraitAdd}>
            Add trait
          </button>
        </fieldset>
      </fieldset>

      <fieldset className="form-fieldset">
        <legend className="form-fieldset__legend">Voice</legend>

        <FieldWrapper
          id="npc-voice-tone"
          label="Overall tone"
          hint="Sets the social register for this character's responses."
          error={errorFor(errors, 'voice.tone')}
        >
          <select
            id="npc-voice-tone"
            className="form-field__select"
            value={str(voice['tone'])}
            onChange={(e) => handleVoiceChange('tone', e.target.value)}
          >
            <option value="">— choose —</option>
            <option value="casual">Casual — relaxed, informal</option>
            <option value="professional">Professional — businesslike but approachable</option>
            <option value="formal">Formal — reserved, precise</option>
          </select>
        </FieldWrapper>

        <FieldWrapper
          id="npc-voice-pace"
          label="Response pace"
          hint="Controls how much the NPC says per turn."
          error={errorFor(errors, 'voice.pace')}
        >
          <select
            id="npc-voice-pace"
            className="form-field__select"
            value={str(voice['pace'])}
            onChange={(e) => handleVoiceChange('pace', e.target.value)}
          >
            <option value="">— choose —</option>
            <option value="slow">Slow — brief, measured replies</option>
            <option value="moderate">Moderate — balanced responses</option>
            <option value="fast">Fast — verbose, talkative</option>
          </select>
        </FieldWrapper>

        <FieldWrapper
          id="npc-voice-formality"
          label="Formality descriptor"
          hint='Additional label used in prompting (e.g. "business-casual", "academic", "street").'
          error={errorFor(errors, 'voice.formality')}
        >
          <input
            id="npc-voice-formality"
            type="text"
            className="form-field__input"
            value={str(voice['formality'])}
            onChange={(e) => handleVoiceChange('formality', e.target.value)}
            maxLength={100}
            placeholder="business-casual"
          />
        </FieldWrapper>
      </fieldset>

      <fieldset className="form-fieldset">
        <legend className="form-fieldset__legend">Hard limits</legend>
        <p className="form-field__hint">
          Behavioural lines this character will not cross regardless of what the player says.
          Safety-relevant limits are enforced at the policy layer in addition to this list.
        </p>
        {errorFor(errors, 'boundaries') && (
          <p className="form-field__error" role="alert">
            {errorFor(errors, 'boundaries')}
          </p>
        )}
        <ul className="form-list" aria-label="Boundary list">
          {boundaries.map((b, i) => (
            <li key={i} className="form-list__item">
              <input
                type="text"
                className="form-field__input form-list__item-input"
                value={str(b)}
                onChange={(e) => handleBoundaryChange(i, e.target.value)}
                placeholder="Does not discuss salary before a formal offer."
                aria-label={`Limit ${i + 1}`}
                maxLength={300}
              />
              <button
                type="button"
                className="form-list__remove-btn"
                onClick={() => handleBoundaryRemove(i)}
                aria-label={`Remove limit ${i + 1}`}
              >
                Remove
              </button>
              {errorFor(errors, `boundaries.${i}`) && (
                <p className="form-field__error" role="alert">
                  {errorFor(errors, `boundaries.${i}`)}
                </p>
              )}
            </li>
          ))}
        </ul>
        <button type="button" className="form-list__add-btn" onClick={handleBoundaryAdd}>
          Add limit
        </button>
      </fieldset>

      <FieldWrapper
        id="npc-hidden-agenda"
        label="Hidden motivation"
        hint="What this character secretly values or wants. Embedded in the AI prompt — never shown to the player."
        error={errorFor(errors, 'hidden_agenda')}
      >
        <textarea
          id="npc-hidden-agenda"
          className="form-field__textarea"
          value={str(values['hidden_agenda'])}
          onChange={(e) => onChange('hidden_agenda', e.target.value)}
          rows={3}
          maxLength={1000}
          placeholder="Is particularly impressed by candidates who ask about team culture..."
        />
      </FieldWrapper>
    </div>
  );
}
