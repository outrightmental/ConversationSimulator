// SPDX-License-Identifier: Apache-2.0
/**
 * SetupStatus — a single selector that answers "should the wizard run?".
 *
 *   never-run  — user has not finished or skipped onboarding (server has no outcome)
 *   incomplete — outcome recorded but engine/model/packs are not all present
 *   ready      — outcome recorded and the system is ready to play
 *
 * The server is authoritative. localStorage is a fast-path mirror only:
 * a cleared webview cache should not resurrect the wizard for a working install.
 */

export type CheckId =
  | 'llm-present'
  | 'packs-seeded'
  | 'llama-cpp-binary'
  | 'disk-space'
  | 'data-dir-writable'
  | 'voice-ready'
  | 'runtime-handshake'

export type SetupStatus =
  | { kind: 'ready' }
  | { kind: 'incomplete'; missing: CheckId[] }
  | { kind: 'never-run' }

export interface SetupStatusResponse {
  kind: 'ready' | 'incomplete' | 'never-run'
  missing?: CheckId[]
  onboarding_outcome?: { outcome: string; recorded_at: string } | null
  pending_install_id?: number | null
}

/**
 * Derive a SetupStatus from a server response.
 * Pure function — easy to test exhaustively.
 */
export function deriveSetupStatus(response: SetupStatusResponse): SetupStatus {
  if (response.kind === 'never-run') return { kind: 'never-run' }
  if (response.kind === 'incomplete') return { kind: 'incomplete', missing: (response.missing ?? []) as CheckId[] }
  return { kind: 'ready' }
}
