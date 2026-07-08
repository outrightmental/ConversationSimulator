// SPDX-License-Identifier: Apache-2.0
import type { RawScenario } from '@convsim/pack-loader';

export interface FakeTurnOutput {
  turn: number;
  player_input: string;
  npc_text: string;
  state_delta: Record<string, number>;
  npc_emotion: string | null;
  session_control: 'continue_session' | 'end_session';
  safety_status: 'ok' | 'redirect' | 'stop';
}

/**
 * Produce a deterministic, structural-only turn output for a scenario.
 *
 * The fake runtime does not invoke a language model. It populates state_delta
 * with the scenario's declared state variables at their default values, always
 * returns session_control=continue_session, safety_status=ok, and sets
 * npc_emotion to null (no model, no generated emotion).
 *
 * This lets CI verify structural expectations — that variables are declared,
 * the session does not terminate unexpectedly, and no safety stop fires —
 * without requiring any model weights.
 */
export function runFakeTurn(
  scenario: RawScenario,
  turn: number,
  playerInput: string,
): FakeTurnOutput {
  return {
    turn,
    player_input: playerInput,
    npc_text: '',
    state_delta: extractStateDefaults(scenario),
    npc_emotion: null,
    session_control: 'continue_session',
    safety_status: 'ok',
  };
}

function extractStateDefaults(scenario: RawScenario): Record<string, number> {
  const state = scenario['state'] as
    | { variables?: Record<string, { default?: number }> }
    | undefined;

  if (!state?.variables) return {};

  return Object.fromEntries(
    Object.entries(state.variables).map(([k, v]) => [k, v.default ?? 0]),
  );
}
