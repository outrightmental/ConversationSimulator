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
  const uid = React.useId();
  const formTabId = `${uid}-form-tab`;
  const yamlTabId = `${uid}-yaml-tab`;
  const formPanelId = `${uid}-form-panel`;
  const yamlPanelId = `${uid}-yaml-panel`;

  const { yaml, formValues, errors, activeTab, setActiveTab, updateField, setYaml } =
    useFormSync(fileType, initialYaml);

  function handleFormChange(path: string, value: unknown) {
    updateField(path, value);
  }

  function handleYamlChange(newYaml: string) {
    setYaml(newYaml);
  }

  // Notify parent whenever yaml changes due to a user edit (form or YAML tab).
  // We must NOT fire when yaml changes because initialYaml prop changed — the
  // parent already holds that value (they just passed it in). We detect prop
  // changes by comparing to the previous initialYaml in the render phase and
  // setting a flag before the yaml effect can fire.
  const isFirstRender = React.useRef(true);
  const suppressNextOnChange = React.useRef(false);
  const prevInitialYaml = React.useRef(initialYaml);
  if (prevInitialYaml.current !== initialYaml) {
    prevInitialYaml.current = initialYaml;
    // Only arm the suppression when yaml will actually change. If yaml is already
    // equal to the new initialYaml, useFormSync's reset effect is a no-op and the
    // [yaml] effect will never fire to clear the flag — leaving it stuck at true
    // and silently dropping the next user-driven onChange call.
    if (yaml !== initialYaml) {
      suppressNextOnChange.current = true;
    }
  }
  React.useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    if (suppressNextOnChange.current) {
      suppressNextOnChange.current = false;
      return;
    }
    onChange?.(yaml);
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
          aria-controls={formPanelId}
          id={formTabId}
          className={`form-editor__tab ${activeTab === 'form' ? 'form-editor__tab--active' : ''}`}
          onClick={() => setActiveTab('form')}
        >
          Form
        </button>
        <button
          role="tab"
          aria-selected={activeTab === 'yaml'}
          aria-controls={yamlPanelId}
          id={yamlTabId}
          className={`form-editor__tab ${activeTab === 'yaml' ? 'form-editor__tab--active' : ''}`}
          onClick={() => setActiveTab('yaml')}
        >
          YAML
        </button>
      </div>

      <div
        id={formPanelId}
        role="tabpanel"
        aria-labelledby={formTabId}
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
        id={yamlPanelId}
        role="tabpanel"
        aria-labelledby={yamlTabId}
        hidden={activeTab !== 'yaml'}
        className="form-editor__panel"
      >
        <YamlPane value={yaml} onChange={handleYamlChange} errors={errors} />
      </div>
    </div>
  );
}
