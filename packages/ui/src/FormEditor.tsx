import React from 'react';
import type { PackFileType } from '@convsim/scenario-schema';
import { ManifestForm } from './forms/ManifestForm.js';
import { NpcForm } from './forms/NpcForm.js';
import { RubricForm } from './forms/RubricForm.js';
import { ScenarioForm } from './forms/ScenarioForm.js';
import { useFormSync } from './hooks/useFormSync.js';
import { YamlPane } from './YamlPane.js';

export interface FormEditorProps {
  /** Which type of pack file is being edited. */
  fileType: PackFileType;
  /**
   * Initial YAML string. Changing this prop resets the editor state.
   * Use a stable string (e.g. from file load) to avoid unnecessary resets.
   */
  initialYaml: string;
  /** Called whenever the YAML content changes (from either form or YAML tab). */
  onChange?: (yaml: string) => void;
  /** Optional CSS class added to the root element. */
  className?: string;
}

const FILE_TYPE_LABELS: Record<PackFileType, string> = {
  manifest: 'Pack manifest',
  scenario: 'Scenario',
  npc: 'Character (NPC)',
  rubric: 'Rubric',
};

/**
 * Dual-pane editor for any pack YAML file.
 *
 * Provides a "Form" tab with creator-friendly fields and a "YAML" tab
 * for direct editing. Both views stay in sync. Unknown YAML fields are
 * preserved when form edits are applied. YAML comments are not preserved
 * (js-yaml limitation — documented in YamlPane).
 *
 * fictional cannot be changed from the form (it must always be true).
 * Executable behaviour cannot be added (pack format is purely declarative).
 */
export function FormEditor({ fileType, initialYaml, onChange, className }: FormEditorProps) {
  const { yaml, formValues, errors, activeTab, setActiveTab, updateField, setYaml } =
    useFormSync(fileType, initialYaml);

  function handleFormChange(path: string, value: unknown) {
    updateField(path, value);
    if (onChange) {
      // YAML will be updated inside updateField; we need the next YAML value.
      // The hook updates yaml synchronously within the state setter, so we
      // call onChange after state has been enqueued. The parent will see the
      // latest value on the next render.
    }
  }

  function handleYamlChange(newYaml: string) {
    setYaml(newYaml);
    onChange?.(newYaml);
  }

  // Notify parent when form field changes update YAML.
  // We use a layout effect to call onChange after render so the parent
  // always receives the post-update YAML string.
  React.useEffect(() => {
    onChange?.(yaml);
    // Only call when yaml changes — not on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [yaml]);

  return (
    <div className={`form-editor ${className ?? ''}`} data-file-type={fileType}>
      <div className="form-editor__header">
        <h2 className="form-editor__title">{FILE_TYPE_LABELS[fileType]}</h2>
        {errors.length > 0 && (
          <span className="form-editor__error-badge" aria-label={`${errors.length} validation errors`}>
            {errors.length} error{errors.length === 1 ? '' : 's'}
          </span>
        )}
      </div>

      <div className="form-editor__tabs" role="tablist">
        <button
          role="tab"
          aria-selected={activeTab === 'form'}
          aria-controls="form-editor-form-panel"
          id="form-editor-form-tab"
          className={`form-editor__tab ${activeTab === 'form' ? 'form-editor__tab--active' : ''}`}
          onClick={() => setActiveTab('form')}
        >
          Form
        </button>
        <button
          role="tab"
          aria-selected={activeTab === 'yaml'}
          aria-controls="form-editor-yaml-panel"
          id="form-editor-yaml-tab"
          className={`form-editor__tab ${activeTab === 'yaml' ? 'form-editor__tab--active' : ''}`}
          onClick={() => setActiveTab('yaml')}
        >
          YAML
        </button>
      </div>

      <div
        id="form-editor-form-panel"
        role="tabpanel"
        aria-labelledby="form-editor-form-tab"
        hidden={activeTab !== 'form'}
        className="form-editor__panel"
      >
        {fileType === 'manifest' && (
          <ManifestForm values={formValues} errors={errors} onChange={handleFormChange} />
        )}
        {fileType === 'scenario' && (
          <ScenarioForm values={formValues} errors={errors} onChange={handleFormChange} />
        )}
        {fileType === 'npc' && (
          <NpcForm values={formValues} errors={errors} onChange={handleFormChange} />
        )}
        {fileType === 'rubric' && (
          <RubricForm values={formValues} errors={errors} onChange={handleFormChange} />
        )}
      </div>

      <div
        id="form-editor-yaml-panel"
        role="tabpanel"
        aria-labelledby="form-editor-yaml-tab"
        hidden={activeTab !== 'yaml'}
        className="form-editor__panel"
      >
        <YamlPane value={yaml} onChange={handleYamlChange} errors={errors} />
      </div>
    </div>
  );
}
