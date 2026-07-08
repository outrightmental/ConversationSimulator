// SPDX-License-Identifier: Apache-2.0

/**
 * Evaluate a check expression against a resolved path value.
 *
 * Supported check forms:
 *   non_empty_string           — value is a non-empty string
 *   min_length_1               — value is an array with length >= 1
 *   equals <literal>           — value === literal (true/false parsed as boolean, numbers as number)
 *   contains <needle>          — array or string includes needle
 *   k=v AND k=v ...            — object has all key=value pairs (numeric values auto-parsed)
 */
export function evaluateCheck(value: unknown, check: string): boolean {
  if (check === 'non_empty_string') {
    return typeof value === 'string' && value.length > 0;
  }

  if (check === 'min_length_1') {
    return Array.isArray(value) && value.length >= 1;
  }

  if (check.startsWith('equals ')) {
    const literal = check.slice('equals '.length).trim();
    return value === parseLiteral(literal);
  }

  if (check.startsWith('contains ')) {
    const needle = check.slice('contains '.length).trim();
    if (Array.isArray(value)) return value.includes(needle);
    if (typeof value === 'string') return value.includes(needle);
    return false;
  }

  if (check.includes(' AND ') || check.includes('=')) {
    return evaluateKeyValueConditions(value, check);
  }

  return false;
}

function parseLiteral(s: string): unknown {
  if (s === 'true') return true;
  if (s === 'false') return false;
  if (s === 'null') return null;
  const n = Number(s);
  if (!isNaN(n) && s.trim() !== '') return n;
  return s;
}

function evaluateKeyValueConditions(value: unknown, check: string): boolean {
  if (typeof value !== 'object' || value === null) return false;

  const obj = value as Record<string, unknown>;
  const conditions = check.split(' AND ').map((c) => c.trim());

  for (const condition of conditions) {
    const eqIdx = condition.indexOf('=');
    if (eqIdx === -1) return false;

    const key = condition.slice(0, eqIdx).trim();
    const rawVal = condition.slice(eqIdx + 1).trim();
    const expected = parseLiteral(rawVal);

    if (obj[key] !== expected) return false;
  }

  return true;
}
