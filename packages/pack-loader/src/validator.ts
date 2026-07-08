// SPDX-License-Identifier: Apache-2.0
import Ajv2020 from 'ajv/dist/2020';
import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { load as yamlLoad } from 'js-yaml';
import { PackLoaderError, SUPPORTED_SCHEMA_VERSION } from './types.js';

const _dir = dirname(fileURLToPath(import.meta.url));
const schemasDir = resolve(_dir, '..', '..', '..', 'schemas');

const ajv = new Ajv2020({ strict: false, validateSchema: false, allErrors: true });

function loadSchema(name: string): object {
  return JSON.parse(readFileSync(resolve(schemasDir, name), 'utf8')) as object;
}

const validators = {
  pack: ajv.compile(loadSchema('pack.schema.json')),
  scenario: ajv.compile(loadSchema('scenario.schema.json')),
  npc: ajv.compile(loadSchema('npc.schema.json')),
  rubric: ajv.compile(loadSchema('rubric.schema.json')),
  safety: ajv.compile(loadSchema('safety.schema.json')),
  scene: ajv.compile(loadSchema('scene.schema.json')),
};

export type SchemaKey = keyof typeof validators;

/**
 * Parse YAML text and validate it against the named JSON schema.
 * Returns the parsed object on success; throws PackLoaderError on failure.
 * Never executes any code from the YAML file — js-yaml uses safe load mode.
 */
export function parseAndValidate<T>(
  yamlText: string,
  schemaKey: SchemaKey,
  filePath: string,
): T {
  let raw: unknown;
  try {
    raw = yamlLoad(yamlText);
  } catch (e) {
    throw new PackLoaderError(
      'INVALID_YAML',
      `YAML parse error in ${filePath}: ${e instanceof Error ? e.message : String(e)}`,
      filePath,
    );
  }

  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
    throw new PackLoaderError(
      'INVALID_YAML',
      `Expected a YAML object in ${filePath}, got ${Array.isArray(raw) ? 'array' : String(raw)}`,
      filePath,
    );
  }

  const data = raw as Record<string, unknown>;

  if (
    typeof data['schema_version'] === 'string' &&
    data['schema_version'] !== SUPPORTED_SCHEMA_VERSION
  ) {
    throw new PackLoaderError(
      'UNSUPPORTED_VERSION',
      `Unsupported schema_version "${data['schema_version']}" in ${filePath}. ` +
        `Expected "${SUPPORTED_SCHEMA_VERSION}".`,
      filePath,
    );
  }

  const validate = validators[schemaKey];
  const ok = validate(raw);
  if (!ok) {
    const errs = (validate.errors ?? [])
      .map((e) => `${e.instancePath || '(root)'}: ${e.message ?? 'invalid'}`)
      .join('; ');
    throw new PackLoaderError(
      'SCHEMA_VALIDATION',
      `Schema validation failed for ${filePath}: ${errs}`,
      filePath,
    );
  }

  return raw as T;
}
