/**
 * Utilities for parsing pack YAML files and merging form edits back to YAML.
 *
 * Comment preservation: js-yaml does not retain YAML comments when round-tripping
 * through a JavaScript object. Comments in the original YAML will be lost after
 * a form-driven edit. Unknown (extra) fields are preserved via deep-merge.
 */
import yaml from 'js-yaml';
import { ZodError, ZodSchema } from 'zod';
import { ManifestSchema, NpcSchema, RubricSchema, ScenarioSchema } from './schemas.js';
import type {
  FieldError,
  NpcFile,
  PackFileType,
  PackManifest,
  ParseResult,
  RubricFile,
  ScenarioFile,
} from './types.js';

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function zodToFieldErrors(err: ZodError): FieldError[] {
  return err.issues.map((issue) => ({
    path: issue.path.join('.') || '(root)',
    message: issue.message,
  }));
}

function parseRaw(yamlStr: string): { value: unknown; error?: FieldError } {
  try {
    return { value: yaml.load(yamlStr) };
  } catch (e) {
    return {
      value: null,
      error: {
        path: '(root)',
        message: `YAML syntax error: ${e instanceof Error ? e.message : String(e)}`,
      },
    };
  }
}

function validateWith<T>(schema: ZodSchema<T>, raw: unknown): ParseResult<T> {
  const result = schema.safeParse(raw);
  if (result.success) {
    return { ok: true, data: result.data, errors: [] };
  }
  return { ok: false, data: null, errors: zodToFieldErrors(result.error) };
}

function isPlainObject(val: unknown): val is Record<string, unknown> {
  return typeof val === 'object' && val !== null && !Array.isArray(val);
}

/**
 * Deep merge `source` into `target`. Values in `source` override those in
 * `target`; keys present only in `target` are preserved (unknown-field safety).
 */
function deepMerge(
  target: Record<string, unknown>,
  source: Record<string, unknown>,
): Record<string, unknown> {
  const result: Record<string, unknown> = { ...target };
  for (const key of Object.keys(source)) {
    const sv = source[key];
    if (sv === undefined) continue;
    const tv = result[key];
    if (isPlainObject(sv) && isPlainObject(tv)) {
      result[key] = deepMerge(tv, sv);
    } else {
      result[key] = sv;
    }
  }
  return result;
}

function toYamlString(obj: Record<string, unknown>): string {
  return yaml.dump(obj, {
    lineWidth: 100,
    quotingType: '"',
    forceQuotes: false,
    noRefs: true,
  });
}

// ---------------------------------------------------------------------------
// Per-type parse functions
// ---------------------------------------------------------------------------

export function parseManifestYaml(yamlStr: string): ParseResult<PackManifest> {
  const { value, error } = parseRaw(yamlStr);
  if (error) return { ok: false, data: null, errors: [error] };
  return validateWith(ManifestSchema, value) as ParseResult<PackManifest>;
}

export function parseScenarioYaml(yamlStr: string): ParseResult<ScenarioFile> {
  const { value, error } = parseRaw(yamlStr);
  if (error) return { ok: false, data: null, errors: [error] };
  return validateWith(ScenarioSchema, value) as ParseResult<ScenarioFile>;
}

export function parseNpcYaml(yamlStr: string): ParseResult<NpcFile> {
  const { value, error } = parseRaw(yamlStr);
  if (error) return { ok: false, data: null, errors: [error] };
  return validateWith(NpcSchema, value) as ParseResult<NpcFile>;
}

export function parseRubricYaml(yamlStr: string): ParseResult<RubricFile> {
  const { value, error } = parseRaw(yamlStr);
  if (error) return { ok: false, data: null, errors: [error] };
  return validateWith(RubricSchema, value) as ParseResult<RubricFile>;
}

// ---------------------------------------------------------------------------
// Per-type YAML serialization (merge form edits back)
// ---------------------------------------------------------------------------

/**
 * Merge `formValues` into `originalYaml` and return updated YAML.
 * Unknown fields in `originalYaml` are preserved.
 */
export function mergeManifestToYaml(
  formValues: Partial<PackManifest>,
  originalYaml: string,
): string {
  const original = safeParseObject(originalYaml);
  return toYamlString(deepMerge(original, formValues as Record<string, unknown>));
}

export function mergeScenarioToYaml(
  formValues: Partial<ScenarioFile>,
  originalYaml: string,
): string {
  const original = safeParseObject(originalYaml);
  return toYamlString(deepMerge(original, formValues as Record<string, unknown>));
}

export function mergeNpcToYaml(formValues: Partial<NpcFile>, originalYaml: string): string {
  const original = safeParseObject(originalYaml);
  return toYamlString(deepMerge(original, formValues as Record<string, unknown>));
}

export function mergeRubricToYaml(formValues: Partial<RubricFile>, originalYaml: string): string {
  const original = safeParseObject(originalYaml);
  return toYamlString(deepMerge(original, formValues as Record<string, unknown>));
}

// ---------------------------------------------------------------------------
// Generic helpers
// ---------------------------------------------------------------------------

function safeParseObject(yamlStr: string): Record<string, unknown> {
  try {
    const parsed = yaml.load(yamlStr);
    return isPlainObject(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

/**
 * Parse a YAML string to a plain object without schema validation.
 * Returns the parsed object, or null if the YAML is syntactically invalid or
 * does not produce a plain object (e.g. a bare scalar or sequence).
 */
export function parseYamlToObject(yamlStr: string): Record<string, unknown> | null {
  try {
    const parsed = yaml.load(yamlStr);
    return isPlainObject(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

/** Dispatch parse by file type. */
export function parseByType(
  fileType: PackFileType,
  yamlStr: string,
): ParseResult<PackManifest | ScenarioFile | NpcFile | RubricFile> {
  switch (fileType) {
    case 'manifest':
      return parseManifestYaml(yamlStr);
    case 'scenario':
      return parseScenarioYaml(yamlStr);
    case 'npc':
      return parseNpcYaml(yamlStr);
    case 'rubric':
      return parseRubricYaml(yamlStr);
  }
}

/** Dispatch merge-to-YAML by file type. */
export function mergeToYaml(
  fileType: PackFileType,
  formValues: Record<string, unknown>,
  originalYaml: string,
): string {
  switch (fileType) {
    case 'manifest':
      return mergeManifestToYaml(formValues as Partial<PackManifest>, originalYaml);
    case 'scenario':
      return mergeScenarioToYaml(formValues as Partial<ScenarioFile>, originalYaml);
    case 'npc':
      return mergeNpcToYaml(formValues as Partial<NpcFile>, originalYaml);
    case 'rubric':
      return mergeRubricToYaml(formValues as Partial<RubricFile>, originalYaml);
  }
}

/**
 * Set a value at a dot-separated path in a nested object.
 * Returns a new object (does not mutate the input).
 */
export function setByPath(
  obj: Record<string, unknown>,
  path: string,
  value: unknown,
): Record<string, unknown> {
  const parts = path.split('.');
  if (parts.length === 1) {
    return { ...obj, [path]: value };
  }
  const [head, ...rest] = parts as [string, ...string[]];
  const nested = isPlainObject(obj[head]) ? (obj[head] as Record<string, unknown>) : {};
  return { ...obj, [head]: setByPath(nested, rest.join('.'), value) };
}

/**
 * Get a value at a dot-separated path in a nested object or array.
 * Numeric path segments (e.g. "goals.0") index into arrays.
 */
export function getByPath(obj: Record<string, unknown>, path: string): unknown {
  const parts = path.split('.');
  let current: unknown = obj;
  for (const part of parts) {
    if (Array.isArray(current)) {
      const index = Number(part);
      if (!Number.isInteger(index) || index < 0) return undefined;
      current = current[index];
    } else if (isPlainObject(current)) {
      current = current[part];
    } else {
      return undefined;
    }
  }
  return current;
}
