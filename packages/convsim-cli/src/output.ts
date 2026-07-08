// SPDX-License-Identifier: Apache-2.0

/**
 * Write a JSON value to stdout as the sole output.  Used in --json mode.
 */
export function writeJson(data: unknown): void {
  process.stdout.write(JSON.stringify(data, null, 2) + '\n');
}

/**
 * Write a line to stdout (human-readable mode).
 */
export function writeLine(text: string): void {
  process.stdout.write(text + '\n');
}

/**
 * Write a line to stderr (human-readable mode).
 */
export function writeErrorLine(text: string): void {
  process.stderr.write(text + '\n');
}

/**
 * Format a file size in bytes as a human-friendly string.
 */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
