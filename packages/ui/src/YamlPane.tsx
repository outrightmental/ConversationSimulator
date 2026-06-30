import React from 'react';
import type { FieldError } from '@convsim/scenario-schema';

interface YamlPaneProps {
  value: string;
  onChange: (newYaml: string) => void;
  errors: FieldError[];
}

/**
 * A plain textarea editor for the raw YAML of a pack file.
 * Displays YAML parse/validation errors below the textarea.
 *
 * Note: YAML comments written here are preserved in the textarea but will be
 * lost when form edits are merged back to YAML (js-yaml does not retain
 * comments through serialization). Advanced fields not covered by the form
 * remain editable here and are preserved across form edits via deep-merge.
 */
export function YamlPane({ value, onChange, errors }: YamlPaneProps) {
  return (
    <div className="yaml-pane">
      <textarea
        className="yaml-pane__editor"
        aria-label="YAML editor"
        spellCheck={false}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      {errors.length > 0 && (
        <ul className="yaml-pane__errors" role="alert" aria-label="YAML validation errors">
          {errors.map((err, i) => (
            <li key={i} className="yaml-pane__error-item">
              <span className="yaml-pane__error-path">{err.path}:</span>{' '}
              <span className="yaml-pane__error-message">{err.message}</span>
            </li>
          ))}
        </ul>
      )}
      <p className="yaml-pane__notice">
        YAML comments and unknown fields are preserved across form edits.
        Comments written here may be removed on the next form save.
      </p>
    </div>
  );
}
