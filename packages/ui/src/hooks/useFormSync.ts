import {
  type FieldError,
  type PackFileType,
  getByPath,
  mergeToYaml,
  parseByType,
  parseYamlToObject,
  setByPath,
} from '@convsim/scenario-schema';
import { useCallback, useEffect, useRef, useState } from 'react';

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

/**
 * Extract form values from a YAML string.
 * On schema validation failure, falls back to the raw parsed object so that
 * fields unrelated to the error remain visible in the form (same behaviour as
 * the YAML-pane-edit path in setYaml).
 */
function extractFormValues(
  fileType: PackFileType,
  yamlStr: string,
): Record<string, unknown> {
  const result = parseByType(fileType, yamlStr);
  if (result.ok) return result.data as Record<string, unknown>;
  return parseYamlToObject(yamlStr) ?? {};
}

export function useFormSync(fileType: PackFileType, initialYaml: string): FormSyncState {
  const [yaml, setYamlInternal] = useState(initialYaml);
  const [formValues, setFormValues] = useState<Record<string, unknown>>(() =>
    extractFormValues(fileType, initialYaml),
  );
  const [errors, setErrors] = useState<FieldError[]>(() => {
    const result = parseByType(fileType, initialYaml);
    return result.ok ? [] : result.errors;
  });
  const [activeTab, setActiveTab] = useState<ActiveTab>('form');

  // Reset all derived state when initialYaml or fileType changes (e.g. user loads a different file).
  // The ref tracks whether the initial mount has already run so we don't discard the
  // lazy-initialised state with a redundant parse on mount.
  const skipResetRef = useRef(true);
  useEffect(() => {
    if (skipResetRef.current) {
      skipResetRef.current = false;
      return;
    }
    const result = parseByType(fileType, initialYaml);
    setYamlInternal(initialYaml);
    setFormValues(extractFormValues(fileType, initialYaml));
    setErrors(result.ok ? [] : result.errors);
    setActiveTab('form');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialYaml, fileType]);

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
        // Even when schema validation fails, update form fields from the raw
        // parsed object (if YAML syntax is valid) so that form and YAML views
        // stay in sync for any field that isn't itself the cause of the error.
        const raw = parseYamlToObject(newYaml);
        if (raw) setFormValues(raw);
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
