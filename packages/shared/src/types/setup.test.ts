import { describe, it, expect } from 'vitest';
import { validateSetup, randomSeed } from './setup.js';
import type { SetupFormValues } from './setup.js';
import type { RuntimeReadiness } from './runtime.js';

const runtimeReady: RuntimeReadiness = {
  llm_ready: true,
  llm_model_name: 'Qwen3 8B',
  stt_ready: true,
  tts_ready: true,
  tts_voice_name: 'af_heart',
  network_required: false,
};

const runtimeTextOnly: RuntimeReadiness = {
  llm_ready: true,
  llm_model_name: 'Qwen3 8B',
  stt_ready: false,
  tts_ready: false,
  tts_voice_name: null,
  network_required: false,
};

const validForm: SetupFormValues = {
  difficulty: 'normal',
  player_role_name: 'Alice',
  language: 'en',
  input_mode: 'text-only',
  tts_enabled: false,
  show_state_meters: false,
  save_transcript: true,
  seed: null,
};

describe('validateSetup', () => {
  it('passes a valid form with all runtime ready', () => {
    const result = validateSetup(
      { ...validForm, input_mode: 'push-to-talk', tts_enabled: true },
      runtimeReady,
      true,
    );
    expect(result.valid).toBe(true);
    expect(result.errors).toHaveLength(0);
  });

  it('fails when TTS is enabled but TTS runtime is not ready', () => {
    const result = validateSetup(
      { ...validForm, tts_enabled: true },
      runtimeTextOnly,
      false,
    );
    expect(result.valid).toBe(false);
    const ttsError = result.errors.find((e) => e.field === 'tts_enabled');
    expect(ttsError).toBeDefined();
    expect(ttsError!.message).toMatch(/TTS/i);
  });

  it('fails when voice input is selected but STT is not ready', () => {
    const result = validateSetup(
      { ...validForm, input_mode: 'push-to-talk' },
      runtimeTextOnly,
      false,
    );
    expect(result.valid).toBe(false);
    const sttError = result.errors.find((e) => e.field === 'input_mode');
    expect(sttError).toBeDefined();
  });

  it('allows text-only input mode even without STT', () => {
    const result = validateSetup(
      { ...validForm, input_mode: 'text-only', tts_enabled: false },
      runtimeTextOnly,
      false,
    );
    expect(result.valid).toBe(true);
  });

  it('fails when show_state_meters is true but not permitted by scenario', () => {
    const result = validateSetup(
      { ...validForm, show_state_meters: true },
      runtimeReady,
      false,
    );
    expect(result.valid).toBe(false);
    const meterError = result.errors.find((e) => e.field === 'show_state_meters');
    expect(meterError).toBeDefined();
  });

  it('passes when show_state_meters is true and permitted', () => {
    const result = validateSetup(
      { ...validForm, show_state_meters: true },
      runtimeReady,
      true,
    );
    expect(result.valid).toBe(true);
  });

  it('fails when player_role_name is empty', () => {
    const result = validateSetup(
      { ...validForm, player_role_name: '' },
      runtimeReady,
      false,
    );
    expect(result.valid).toBe(false);
    const nameError = result.errors.find((e) => e.field === 'player_role_name');
    expect(nameError).toBeDefined();
  });

  it('fails when player_role_name is only whitespace', () => {
    const result = validateSetup(
      { ...validForm, player_role_name: '   ' },
      runtimeReady,
      false,
    );
    expect(result.valid).toBe(false);
  });

  it('can return multiple errors simultaneously', () => {
    const result = validateSetup(
      { ...validForm, player_role_name: '', tts_enabled: true },
      runtimeTextOnly,
      false,
    );
    expect(result.errors.length).toBeGreaterThanOrEqual(2);
  });

  it('fails when seed exceeds 2147483647', () => {
    const result = validateSetup(
      { ...validForm, seed: 2147483648 },
      runtimeReady,
      false,
    );
    expect(result.valid).toBe(false);
    const seedError = result.errors.find((e) => e.field === 'seed');
    expect(seedError).toBeDefined();
    expect(seedError!.message).toMatch(/seed/i);
  });

  it('fails when seed is negative', () => {
    const result = validateSetup(
      { ...validForm, seed: -1 },
      runtimeReady,
      false,
    );
    expect(result.valid).toBe(false);
    expect(result.errors.find((e) => e.field === 'seed')).toBeDefined();
  });

  it('passes when seed is exactly at the upper bound', () => {
    const result = validateSetup(
      { ...validForm, seed: 2147483647 },
      runtimeReady,
      false,
    );
    expect(result.valid).toBe(true);
  });

  it('passes when seed is 0 (lower bound)', () => {
    const result = validateSetup({ ...validForm, seed: 0 }, runtimeReady, false);
    expect(result.valid).toBe(true);
  });

  it('fails when seed is NaN', () => {
    const result = validateSetup({ ...validForm, seed: NaN }, runtimeReady, false);
    expect(result.valid).toBe(false);
    expect(result.errors.find((e) => e.field === 'seed')).toBeDefined();
  });

  it('fails when seed is a non-integer float', () => {
    const result = validateSetup({ ...validForm, seed: 1.5 }, runtimeReady, false);
    expect(result.valid).toBe(false);
    expect(result.errors.find((e) => e.field === 'seed')).toBeDefined();
  });
});

describe('randomSeed', () => {
  it('returns a non-negative integer', () => {
    const s = randomSeed();
    expect(Number.isInteger(s)).toBe(true);
    expect(s).toBeGreaterThanOrEqual(0);
  });

  it('returns values within 31-bit range', () => {
    for (let i = 0; i < 50; i++) {
      const s = randomSeed();
      expect(s).toBeLessThan(2 ** 31);
    }
  });
});
