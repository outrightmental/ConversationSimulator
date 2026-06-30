import React from 'react';
import type { FieldError } from '@convsim/scenario-schema';

interface RubricFormProps {
  values: Record<string, unknown>;
  errors: FieldError[];
  onChange: (path: string, value: unknown) => void;
}

function str(v: unknown): string {
  return typeof v === 'string' ? v : '';
}

function num(v: unknown, fallback = 0): number {
  return typeof v === 'number' ? v : fallback;
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
 * Form panel for editing a rubric YAML file.
 *
 * Covers: title and the full list of evaluation dimensions
 * (id, label, description, weight, max_score).
 */
export function RubricForm({ values, errors, onChange }: RubricFormProps) {
  const dimensions = Array.isArray(values['dimensions'])
    ? (values['dimensions'] as Array<Record<string, unknown>>)
    : [];

  function handleDimChange(i: number, field: string, value: unknown) {
    const updated = dimensions.map((d, idx) => (idx === i ? { ...d, [field]: value } : d));
    onChange('dimensions', updated);
  }

  function handleDimAdd() {
    onChange('dimensions', [
      ...dimensions,
      { id: '', label: '', description: '', weight: 1.0, max_score: 5 },
    ]);
  }

  function handleDimRemove(i: number) {
    onChange('dimensions', dimensions.filter((_, idx) => idx !== i));
  }

  return (
    <div className="rubric-form" role="form" aria-label="Rubric editor">
      <FieldWrapper
        id="rubric-title"
        label="Rubric title"
        hint="Displayed on the debrief screen after the conversation ends."
        error={errorFor(errors, 'title')}
      >
        <input
          id="rubric-title"
          type="text"
          className="form-field__input"
          value={str(values['title'])}
          onChange={(e) => onChange('title', e.target.value)}
          maxLength={120}
          placeholder="Interview Performance"
        />
      </FieldWrapper>

      <fieldset className="form-fieldset">
        <legend className="form-fieldset__legend">Evaluation dimensions</legend>
        <p className="form-field__hint">
          Each dimension is tracked turn-by-turn by the AI and shown on the debrief screen.
          Higher weight = more impact on the total score.
        </p>
        {errorFor(errors, 'dimensions') && (
          <p className="form-field__error" role="alert">
            {errorFor(errors, 'dimensions')}
          </p>
        )}

        {dimensions.map((dim, i) => (
          <div key={i} className="form-card">
            <div className="form-card__header">
              <span className="form-card__title">
                Dimension {i + 1}{str(dim['label']) ? `: ${str(dim['label'])}` : ''}
              </span>
              <button
                type="button"
                className="form-list__remove-btn"
                onClick={() => handleDimRemove(i)}
                aria-label={`Remove dimension ${i + 1}`}
              >
                Remove
              </button>
            </div>

            <FieldWrapper
              id={`dim-${i}-label`}
              label="Dimension name"
              hint='Player-visible label on the debrief screen (e.g. "Communication Clarity").'
              error={errorFor(errors, `dimensions.${i}.label`)}
            >
              <input
                id={`dim-${i}-label`}
                type="text"
                className="form-field__input"
                value={str(dim['label'])}
                onChange={(e) => handleDimChange(i, 'label', e.target.value)}
                maxLength={60}
                placeholder="Communication Clarity"
              />
            </FieldWrapper>

            <FieldWrapper
              id={`dim-${i}-description`}
              label="What to look for"
              hint="Instructions for the AI — what player behaviour earns points in this dimension."
              error={errorFor(errors, `dimensions.${i}.description`)}
            >
              <textarea
                id={`dim-${i}-description`}
                className="form-field__textarea"
                value={str(dim['description'])}
                onChange={(e) => handleDimChange(i, 'description', e.target.value)}
                rows={2}
                maxLength={300}
                placeholder="Does the player explain ideas clearly without rambling?"
              />
            </FieldWrapper>

            <div className="form-row">
              <FieldWrapper
                id={`dim-${i}-weight`}
                label="Weight"
                hint="Relative importance (0.1–5.0)."
                error={errorFor(errors, `dimensions.${i}.weight`)}
              >
                <input
                  id={`dim-${i}-weight`}
                  type="number"
                  className="form-field__input form-field__input--short"
                  value={num(dim['weight'], 1)}
                  min={0.1}
                  max={5.0}
                  step={0.1}
                  onChange={(e) => handleDimChange(i, 'weight', Number(e.target.value))}
                />
              </FieldWrapper>

              <FieldWrapper
                id={`dim-${i}-max-score`}
                label="Max points"
                hint="Highest score possible (1–10)."
                error={errorFor(errors, `dimensions.${i}.max_score`)}
              >
                <input
                  id={`dim-${i}-max-score`}
                  type="number"
                  className="form-field__input form-field__input--short"
                  value={num(dim['max_score'], 5)}
                  min={1}
                  max={10}
                  step={1}
                  onChange={(e) => handleDimChange(i, 'max_score', Number(e.target.value))}
                />
              </FieldWrapper>
            </div>
          </div>
        ))}

        <button type="button" className="form-list__add-btn" onClick={handleDimAdd}>
          Add dimension
        </button>
      </fieldset>
    </div>
  );
}
