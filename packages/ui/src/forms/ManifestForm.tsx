import React from 'react';
import type { FieldError } from '@convsim/scenario-schema';
import { FieldWrapper, errorFor, str } from './shared.js';

interface ManifestFormProps {
  values: Record<string, unknown>;
  errors: FieldError[];
  onChange: (path: string, value: unknown) => void;
}

/**
 * Form panel for editing pack manifest metadata.
 *
 * fictional is intentionally not editable — it must always be true for MVP.
 * schema_version is not editable (set by the pack tools, not the creator).
 */
export function ManifestForm({ values, errors, onChange }: ManifestFormProps) {
  const tags = Array.isArray(values['tags']) ? (values['tags'] as string[]) : [];

  function handleTagAdd() {
    onChange('tags', [...tags, '']);
  }

  function handleTagChange(index: number, value: string) {
    const updated = tags.map((t, i) => (i === index ? value : t));
    onChange('tags', updated);
  }

  function handleTagRemove(index: number) {
    onChange('tags', tags.filter((_, i) => i !== index));
  }

  return (
    <div className="manifest-form" role="form" aria-label="Pack manifest editor">
      <FieldWrapper
        id="manifest-id"
        label="Pack ID"
        hint="Unique kebab-case identifier for this pack (e.g. job-interview-basic). Cannot be changed after publishing."
        error={errorFor(errors, 'id')}
      >
        <input
          id="manifest-id"
          type="text"
          className="form-field__input"
          value={str(values['id'])}
          onChange={(e) => onChange('id', e.target.value)}
          maxLength={64}
          placeholder="my-pack-id"
          pattern="[a-z][a-z0-9-]*"
        />
      </FieldWrapper>

      <FieldWrapper
        id="manifest-name"
        label="Pack name"
        hint="Display name shown in the library (e.g. Job Interview Practice)."
        error={errorFor(errors, 'name')}
      >
        <input
          id="manifest-name"
          type="text"
          className="form-field__input"
          value={str(values['name'])}
          onChange={(e) => onChange('name', e.target.value)}
          placeholder="My Scenario Pack"
          maxLength={80}
        />
      </FieldWrapper>

      <FieldWrapper
        id="manifest-version"
        label="Version"
        hint="Semantic version (e.g. 1.0.0). Increment when publishing updates."
        error={errorFor(errors, 'version')}
      >
        <input
          id="manifest-version"
          type="text"
          className="form-field__input"
          value={str(values['version'])}
          onChange={(e) => onChange('version', e.target.value)}
          placeholder="1.0.0"
        />
      </FieldWrapper>

      <FieldWrapper
        id="manifest-description"
        label="Description"
        hint="Short summary shown in the library before players start. Up to 500 characters."
        error={errorFor(errors, 'description')}
      >
        <textarea
          id="manifest-description"
          className="form-field__textarea"
          value={str(values['description'])}
          onChange={(e) => onChange('description', e.target.value)}
          rows={3}
          maxLength={500}
          placeholder="Practice difficult conversations with a fictional character..."
        />
      </FieldWrapper>

      <FieldWrapper
        id="manifest-author"
        label="Author"
        hint="Your name or organization."
        error={errorFor(errors, 'author')}
      >
        <input
          id="manifest-author"
          type="text"
          className="form-field__input"
          value={str(values['author'])}
          onChange={(e) => onChange('author', e.target.value)}
          placeholder="Your Name"
          maxLength={200}
        />
      </FieldWrapper>

      <FieldWrapper
        id="manifest-license"
        label="License"
        hint="SPDX license identifier (e.g. Apache-2.0, MIT, CC-BY-4.0)."
        error={errorFor(errors, 'license')}
      >
        <input
          id="manifest-license"
          type="text"
          className="form-field__input"
          value={str(values['license'])}
          onChange={(e) => onChange('license', e.target.value)}
          placeholder="Apache-2.0"
          maxLength={64}
        />
      </FieldWrapper>

      <fieldset className="form-fieldset">
        <legend className="form-fieldset__legend">Tags</legend>
        <p className="form-field__hint">
          Lowercase keywords that help players find this pack (e.g. interview, negotiation).
        </p>
        {errorFor(errors, 'tags') && (
          <p className="form-field__error" role="alert">
            {errorFor(errors, 'tags')}
          </p>
        )}
        <ul className="form-list" aria-label="Tag list">
          {tags.map((tag, i) => (
            <li key={i} className="form-list__item">
              <input
                type="text"
                className="form-field__input form-list__item-input"
                value={str(tag)}
                onChange={(e) => handleTagChange(i, e.target.value)}
                placeholder="interview"
                aria-label={`Tag ${i + 1}`}
                pattern="[a-z][a-z0-9-]*"
              />
              <button
                type="button"
                className="form-list__remove-btn"
                onClick={() => handleTagRemove(i)}
                aria-label={`Remove tag ${i + 1}`}
              >
                Remove
              </button>
              {errorFor(errors, `tags.${i}`) && (
                <p className="form-field__error" role="alert">
                  {errorFor(errors, `tags.${i}`)}
                </p>
              )}
            </li>
          ))}
        </ul>
        <button type="button" className="form-list__add-btn" onClick={handleTagAdd}>
          Add tag
        </button>
      </fieldset>

      <div className="form-field form-field--readonly">
        <span className="form-field__label">Content declaration</span>
        <p className="form-field__hint">
          <strong>fictional: true</strong> — All characters and situations in this pack must be
          entirely fictional. Real-person impersonation is not permitted.
        </p>
      </div>
    </div>
  );
}
