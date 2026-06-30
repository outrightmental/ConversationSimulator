import {
  type FieldError,
  type PackFileType,
  getByPath,
  mergeToYaml,
  parseByType,
  setByPath,
} from '@convsim/scenario-schema';
import { useCallback, useState } from 'react';

export type ActiveTab = 'form' | 'yaml';

export interface FormSyncState {
  /** Current YAML string (kept in sync with formValues). */
  yaml: string;
  /** Parsed form values as a plain object (may be partial during editing). */
  formValues: Record<string, unknown>;
  /** Field-level validation errors. */
  errors: FieldError[];
  /** Which tab is currently shown. */
  activeTab: ActiveTab;
  setActiveTab: (tab: ActiveTab) => void;
  /**
   * Update a single field by dot-path (e.g. 'state_defaults.trust').
   * Triggers YAML resync and validation.
   */
  updateField: (path: string, value: unknown) => void;
  /**
   * Replace the YAML directly (user editing the YAML tab).
   * Parses and updates form values; sets errors on parse failure.
   */
  setYaml: (newYaml: string) => void;
  /** Read a value from formValues by dot-path. */
  getField: (path: string) => unknown;
}

function parseInitialValues(
  fileType: PackFileType,
  initialYaml: string,
): Record<string, unknown> {
  const result = parseByType(fileType, initialYaml);
  return result.ok ? (result.data as Record<string, unknown>) : {};
}

export function useFormSync(fileType: PackFileType, initialYaml: string): FormSyncState {
  const [yaml, setYamlInternal] = useState(initialYaml);
  const [formValues, setFormValues] = useState<Record<string, unknown>>(() =>
    parseInitialValues(fileType, initialYaml),
  );
  const [errors, setErrors] = useState<FieldError[]>([]);
  const [activeTab, setActiveTab] = useState<ActiveTab>('form');

  const updateField = useCallback(
    (path: string, value: unknown) => {
      setFormValues((prev) => {
        const updated = setByPath(prev, path, value);
        const newYaml = mergeToYaml(fileType, updated, yaml);
        setYamlInternal(newYaml);
        const parseResult = parseByType(fileType, newYaml);
        setErrors(parseResult.ok ? [] : parseResult.errors);
        return updated;
      });
    },
    // yaml captured via closure; stable enough for form editing
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [fileType, yaml],
  );

  const setYaml = useCallback(
    (newYaml: string) => {
      setYamlInternal(newYaml);
      const result = parseByType(fileType, newYaml);
      if (result.ok) {
        setFormValues(result.data as Record<string, unknown>);
        setErrors([]);
      } else {
        setErrors(result.errors);
      }
    },
    [fileType],
  );

  const getField = useCallback(
    (path: string) => getByPath(formValues, path),
    [formValues],
  );

  return { yaml, formValues, errors, activeTab, setActiveTab, updateField, setYaml, getField };
}
