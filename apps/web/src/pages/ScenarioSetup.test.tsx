import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act, within } from '@testing-library/react';
import axe from 'axe-core';
import { ScenarioSetupPage } from './ScenarioSetup';
import type { ScenarioInfo, HealthResponse, SessionCreateResponse } from '@convsim/shared';
import type { ApiResult } from '../api/errors';

const mockScenario: ScenarioInfo = {
  scenario_id: 'behavioral_interview',
  title: 'Behavioral Interview',
  summary: 'A mid-level job interview focused on communication and self-awareness.',
  content_rating: 'PG',
  pack_id: 'official.job_interview_basic',
  pack_name: 'Job Interview Basics',
  player_role: {
    label: 'Candidate',
    brief: 'You are interviewing for a product manager role.',
  },
  difficulty: {
    default: 'standard',
    options: {
      warm:     { patience: 80, volatility: 20, disclosure: 70, time_pressure: 20, label: 'Warm-up', description: 'NPC is patient and guides you.' },
      standard: { patience: 50, volatility: 50, disclosure: 50, time_pressure: 50 },
      hard:     { patience: 25, volatility: 70, disclosure: 25, time_pressure: 60 },
    },
  },
  supported_languages: ['en', 'es'],
  duration: { max_turns: 18, soft_time_limit_minutes: 20 },
  state_meters_permitted: true,
  voice_supported: true,
  safety_summary: 'PG content only. No NSFW, no real-person impersonation.',
  estimated_length_label: '15–20 minutes',
};

const healthReady: HealthResponse = {
  status: 'ok',
  version: '0.1.0',
  runtime: {
    llm_ready: true,
    llm_model_name: 'Qwen3 8B',
    stt_ready: true,
    tts_ready: true,
    tts_voice_name: 'af_heart',
    network_required: false,
  },
};

const healthTextOnly: HealthResponse = {
  status: 'degraded',
  version: '0.1.0',
  runtime: {
    llm_ready: true,
    llm_model_name: 'Qwen3 8B',
    stt_ready: false,
    tts_ready: false,
    tts_voice_name: null,
    network_required: false,
  },
};

vi.mock('../api/client', () => ({
  api: {
    getScenario: vi.fn(),
    health: vi.fn(),
    createSession: vi.fn(),
    listVoices: vi.fn(),
  },
  // Read by api/diag when the submit error card's "Copy diagnostics" button
  // assembles its report.
  getLogExcerptRaw: vi.fn().mockResolvedValue({
    excerpt: 'ConversationSimulator log excerpt\n── app.log ──\nRequest validation failed for POST /api/sessions: tts_voice_id=string_type',
    sources: ['app.log'],
    notice: 'Log excerpt assembled locally.',
  }),
}));

import { api } from '../api/client';
const mockApi = vi.mocked(api);

function renderSetup(overrides?: Partial<Parameters<typeof ScenarioSetupPage>[0]>) {
  const onSessionCreated = vi.fn();
  const onBack = vi.fn();
  render(
    <ScenarioSetupPage
      scenarioId="behavioral_interview"
      onSessionCreated={onSessionCreated}
      onBack={onBack}
      {...overrides}
    />,
  );
  return { onSessionCreated, onBack };
}

const STUB_VOICES = {
  voices: [
    { voice_id: 'af_heart', display_name: 'Heart (US female)', engine: 'kokoro', gender: 'female' as const, locale: 'en-US' },
    { voice_id: 'am_adam', display_name: 'Adam (US male)', engine: 'kokoro', gender: 'male' as const, locale: 'en-US' },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  mockApi.listVoices.mockResolvedValue({ ok: true as const, data: STUB_VOICES });
});

describe('ScenarioSetupPage', () => {
  describe('initial load', () => {
    it('shows a loading state before data arrives', () => {
      mockApi.getScenario.mockReturnValue(new Promise(() => {}));
      mockApi.health.mockReturnValue(new Promise(() => {}));
      renderSetup();
      expect(screen.getByText(/loading scenario/i)).toBeInTheDocument();
    });

    it('renders the form after data loads', async () => {
      mockApi.getScenario.mockResolvedValue({ ok: true as const, data: mockScenario });
      mockApi.health.mockResolvedValue({ ok: true as const, data: healthReady });
      renderSetup();
      await waitFor(() =>
        expect(screen.getByText('Behavioral Interview')).toBeInTheDocument(),
      );
      expect(screen.getByTestId('setup-page')).toBeInTheDocument();
      expect(screen.getByText('Job Interview Basics')).toBeInTheDocument();
    });

    it('shows load error when API fails', async () => {
      mockApi.getScenario.mockResolvedValue({ ok: false as const, error: { kind: 'network' as const, message: 'Network error' } });
      mockApi.health.mockResolvedValue({ ok: true as const, data: healthReady });
      renderSetup();
      await waitFor(() =>
        expect(screen.getByText(/failed to load scenario/i)).toBeInTheDocument(),
      );
    });

    it('renders the form in text-only mode when health endpoint fails', async () => {
      mockApi.getScenario.mockResolvedValue({ ok: true as const, data: mockScenario });
      mockApi.health.mockResolvedValue({ ok: false as const, error: { kind: 'network' as const, message: 'Health unavailable' } });
      renderSetup();
      await waitFor(() =>
        expect(screen.getByText('Behavioral Interview')).toBeInTheDocument(),
      );
      const textOnlyRadio = screen.getByRole('radio', { name: /text only/i });
      expect(textOnlyRadio).toBeChecked();
      const ttsCheckbox = screen.getByRole('checkbox', { name: /npc voice/i });
      expect(ttsCheckbox).toBeDisabled();
    });
  });

  describe('defaults', () => {
    beforeEach(() => {
      mockApi.getScenario.mockResolvedValue({ ok: true as const, data: mockScenario });
      mockApi.health.mockResolvedValue({ ok: true as const, data: healthReady });
    });

    it('sets difficulty to the scenario default', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      const standardRadio = screen.getByRole('radio', { name: /standard/i });
      expect(standardRadio).toBeChecked();
    });

    it('sets player role name to the scenario label', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      const nameInput = screen.getByRole('textbox', {
        name: /name to use in this session/i,
      });
      expect((nameInput as HTMLInputElement).value).toBe('Candidate');
    });

    it('sets language to first supported language', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      const select = screen.getByRole('combobox', {
        name: /conversation language/i,
      });
      expect((select as HTMLSelectElement).value).toBe('en');
    });

    it('enables TTS when TTS runtime is ready and scenario supports voice', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      const ttsCheckbox = screen.getByRole('checkbox', { name: /npc voice/i });
      expect(ttsCheckbox).toBeChecked();
    });

    it('disables TTS by default when scenario does not support voice even if TTS is ready', async () => {
      mockApi.getScenario.mockResolvedValue({ ok: true as const, data: { ...mockScenario, voice_supported: false } });
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      const ttsCheckbox = screen.getByRole('checkbox', { name: /npc voice/i });
      expect(ttsCheckbox).not.toBeChecked();
    });

    it('shows a note when scenario is text-only but TTS is technically available', async () => {
      mockApi.getScenario.mockResolvedValue({ ok: true as const, data: { ...mockScenario, voice_supported: false } });
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      expect(screen.getByText(/designed for text/i)).toBeInTheDocument();
    });

    it('sets input mode to push-to-talk when STT is ready', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      const pttRadio = screen.getByRole('radio', { name: /push-to-talk/i });
      expect(pttRadio).toBeChecked();
    });

    it('enables transcript saving by default', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      const transcriptCheckbox = screen.getByRole('checkbox', {
        name: /save transcript locally/i,
      });
      expect(transcriptCheckbox).toBeChecked();
    });
  });

  describe('difficulty selection', () => {
    beforeEach(() => {
      mockApi.getScenario.mockResolvedValue({ ok: true as const, data: mockScenario });
      mockApi.health.mockResolvedValue({ ok: true as const, data: healthReady });
    });

    it('renders all difficulty options from the scenario', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      expect(screen.getByRole('radio', { name: /warm-up/i })).toBeInTheDocument();
      expect(screen.getByRole('radio', { name: /standard/i })).toBeInTheDocument();
      expect(screen.getByRole('radio', { name: /hard/i })).toBeInTheDocument();
    });

    it('changes difficulty when a different option is selected', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      const hardRadio = screen.getByRole('radio', { name: /hard/i });
      fireEvent.click(hardRadio);
      expect(hardRadio).toBeChecked();
    });
  });

  describe('validation', () => {
    beforeEach(() => {
      mockApi.getScenario.mockResolvedValue({ ok: true as const, data: mockScenario });
      mockApi.health.mockResolvedValue({ ok: true as const, data: healthTextOnly });
    });

    it('disables TTS checkbox when TTS is not available', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      const ttsCheckbox = screen.getByRole('checkbox', { name: /npc voice/i });
      expect(ttsCheckbox).toBeDisabled();
    });

    it('disables voice input options when STT is not available', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      const pttRadio = screen.getByRole('radio', { name: /push-to-talk/i });
      expect(pttRadio).toBeDisabled();
    });

    it('disables hands-free voice input when STT is not available', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      const handsFreeRadio = screen.getByRole('radio', { name: /hands-free/i });
      expect(handsFreeRadio).toBeDisabled();
    });

    it('text-only mode is always available even without STT', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      const textOnlyRadio = screen.getByRole('radio', { name: /text only/i });
      expect(textOnlyRadio).not.toBeDisabled();
    });

    it('shows TTS fallback message when TTS is not available', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      expect(
        screen.getByText(/Install a TTS model to enable voice output/i),
      ).toBeInTheDocument();
    });

    it('shows STT not loaded badge on voice input options when STT is not available', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      const sttBadges = screen.getAllByText(/STT not loaded/i);
      expect(sttBadges.length).toBeGreaterThanOrEqual(2);
    });

    it('shows error when player name is cleared', async () => {
      mockApi.getScenario.mockResolvedValue({ ok: true as const, data: mockScenario });
      mockApi.health.mockResolvedValue({ ok: true as const, data: healthReady });
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      const nameInput = screen.getByRole('textbox', {
        name: /name to use in this session/i,
      });
      fireEvent.change(nameInput, { target: { value: '' } });
      const submitBtn = screen.getByRole('button', { name: /start conversation/i });
      expect(submitBtn).toBeDisabled();
    });
  });

  describe('voice selection', () => {
    beforeEach(() => {
      mockApi.getScenario.mockResolvedValue({ ok: true as const, data: mockScenario });
      mockApi.health.mockResolvedValue({ ok: true as const, data: healthReady });
    });

    it('shows voice dropdown when TTS is enabled and voices are available', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      expect(screen.getByRole('combobox', { name: /npc voice selection/i })).toBeInTheDocument();
    });

    it('hides voice dropdown when TTS is disabled', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      const ttsCheckbox = screen.getByRole('checkbox', { name: /npc voice/i });
      fireEvent.click(ttsCheckbox);
      expect(screen.queryByRole('combobox', { name: /npc voice selection/i })).not.toBeInTheDocument();
    });

    it('populates voice dropdown with voices from the API', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      const voiceSelect = screen.getByRole('combobox', { name: /npc voice selection/i });
      expect(voiceSelect).toBeInTheDocument();
      expect(screen.getByRole('option', { name: /Heart \(US female\)/i })).toBeInTheDocument();
      expect(screen.getByRole('option', { name: /Adam \(US male\)/i })).toBeInTheDocument();
    });

    it('uses stored preferred voice from localStorage as the default', async () => {
      localStorage.setItem('convsim.voice.preferredVoiceId', 'am_adam');
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      const voiceSelect = screen.getByRole('combobox', { name: /npc voice selection/i }) as HTMLSelectElement;
      expect(voiceSelect.value).toBe('am_adam');
    });

    it('defaults to the first voice when no preference is stored', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      const voiceSelect = screen.getByRole('combobox', { name: /npc voice selection/i }) as HTMLSelectElement;
      expect(voiceSelect.value).toBe('af_heart');
    });
  });

  describe('seed controls', () => {
    beforeEach(() => {
      mockApi.getScenario.mockResolvedValue({ ok: true as const, data: mockScenario });
      mockApi.health.mockResolvedValue({ ok: true as const, data: healthReady });
    });

    it('shows auto placeholder when seed is null', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      const seedInput = screen.getByRole('spinbutton', {
        name: /variation seed value/i,
      });
      expect((seedInput as HTMLInputElement).placeholder).toBe('Auto');
      expect((seedInput as HTMLInputElement).value).toBe('');
    });

    it('randomize button sets a numeric seed', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      const randomizeBtn = screen.getByRole('button', { name: /randomize/i });
      fireEvent.click(randomizeBtn);
      const seedInput = screen.getByRole('spinbutton', {
        name: /variation seed value/i,
      }) as HTMLInputElement;
      expect(seedInput.value).not.toBe('');
      expect(Number(seedInput.value)).toBeGreaterThanOrEqual(0);
    });

    it('auto button resets seed to null', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      const randomizeBtn = screen.getByRole('button', { name: /randomize/i });
      fireEvent.click(randomizeBtn);
      const autoBtn = screen.getByRole('button', { name: /^auto$/i });
      fireEvent.click(autoBtn);
      const seedInput = screen.getByRole('spinbutton', {
        name: /variation seed value/i,
      }) as HTMLInputElement;
      expect(seedInput.value).toBe('');
    });

    it('allows manual seed entry', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      const seedInput = screen.getByRole('spinbutton', {
        name: /variation seed value/i,
      });
      fireEvent.change(seedInput, { target: { value: '1234' } });
      expect((seedInput as HTMLInputElement).value).toBe('1234');
    });

    it('shows an error and disables submit when seed is out of range', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      const seedInput = screen.getByRole('spinbutton', {
        name: /variation seed value/i,
      });
      fireEvent.change(seedInput, { target: { value: '3000000000' } });
      await waitFor(() =>
        expect(screen.getByText(/seed must be a whole number between/i)).toBeInTheDocument(),
      );
      expect(screen.getByRole('button', { name: /start conversation/i })).toBeDisabled();
    });

    it('shows an error and disables submit when seed is a decimal', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      const seedInput = screen.getByRole('spinbutton', {
        name: /variation seed value/i,
      });
      fireEvent.change(seedInput, { target: { value: '1.5' } });
      await waitFor(() =>
        expect(screen.getByText(/seed must be a whole number between/i)).toBeInTheDocument(),
      );
      expect(screen.getByRole('button', { name: /start conversation/i })).toBeDisabled();
    });
  });

  describe('session creation', () => {
    beforeEach(() => {
      mockApi.getScenario.mockResolvedValue({ ok: true as const, data: mockScenario });
      mockApi.health.mockResolvedValue({ ok: true as const, data: healthReady });
    });

    it('calls createSession with all setup fields on submit', async () => {
      const mockSession: SessionCreateResponse = {
        session_id: 'sess-123',
        scenario_id: 'behavioral_interview',
        state: 'NotStarted',
        created_at: '2026-06-30T00:00:00Z',
        setup: {
          scenario_id: 'behavioral_interview',
          difficulty: 'standard',
          player_role_name: 'Candidate',
          language: 'en',
          input_mode: 'push-to-talk',
          tts_enabled: true,
          tts_voice_id: 'af_heart',
          show_state_meters: false,
          save_transcript: true,
          seed: null,
        },
      };
      mockApi.createSession.mockResolvedValue({ ok: true as const, data: mockSession });

      const { onSessionCreated } = renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));

      const submitBtn = screen.getByRole('button', { name: /start conversation/i });
      fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(mockApi.createSession).toHaveBeenCalledWith({
          scenario_id: 'behavioral_interview',
          difficulty: 'standard',
          player_role_name: 'Candidate',
          language: 'en',
          input_mode: 'push-to-talk',
          tts_enabled: true,
          tts_voice_id: 'af_heart',
          show_state_meters: false,
          save_transcript: true,
          seed: null,
        });
      });

      await waitFor(() => {
        expect(onSessionCreated).toHaveBeenCalledWith(mockSession);
      });
    });

    it('sends seed in the payload when set', async () => {
      mockApi.createSession.mockResolvedValue({ ok: true as const, data: {
        session_id: 'sess-456',
        scenario_id: 'behavioral_interview',
        state: 'NotStarted',
        created_at: '2026-06-30T00:00:00Z',
        setup: {} as SessionCreateResponse['setup'],
      } });

      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));

      const seedInput = screen.getByRole('spinbutton', {
        name: /variation seed value/i,
      });
      fireEvent.change(seedInput, { target: { value: '9999' } });

      const submitBtn = screen.getByRole('button', { name: /start conversation/i });
      fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(mockApi.createSession).toHaveBeenCalledWith(
          expect.objectContaining({ seed: 9999 }),
        );
      });
    });

    it('shows error message when createSession fails', async () => {
      mockApi.createSession.mockResolvedValue({ ok: false as const, error: { kind: 'http-error' as const, message: 'Server error', status: 500 } });

      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));

      const submitBtn = screen.getByRole('button', { name: /start conversation/i });
      fireEvent.click(submitBtn);

      await waitFor(() =>
        expect(screen.getByRole('alert')).toHaveTextContent(/Request failed/i),
      );
    });

    it('shows designed error state not raw JSON when createSession fails', async () => {
      mockApi.createSession.mockResolvedValue({ ok: false as const, error: { kind: 'http-error' as const, message: 'Unknown scenario_id: behavioral_interview', status: 400 } });

      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));

      const submitBtn = screen.getByRole('button', { name: /start conversation/i });
      fireEvent.click(submitBtn);

      await waitFor(() => {
        const alert = screen.getByRole('alert');
        expect(alert).toHaveTextContent(/Request failed/i);
        expect(alert).not.toHaveTextContent('"statusCode"');
      });
    });

    it('disables submit button while submitting', async () => {
      let resolveSession!: (v: ApiResult<SessionCreateResponse>) => void;
      mockApi.createSession.mockReturnValue(
        new Promise<ApiResult<SessionCreateResponse>>((resolve) => {
          resolveSession = resolve;
        }),
      );

      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));

      const submitBtn = screen.getByRole('button', { name: /start conversation/i });
      fireEvent.click(submitBtn);

      await waitFor(() =>
        expect(screen.getByRole('button', { name: /starting/i })).toBeDisabled(),
      );

      await act(async () => {
        resolveSession({ ok: true as const, data: {
          session_id: 'sess-789',
          scenario_id: 'behavioral_interview',
          state: 'NotStarted',
          created_at: '2026-06-30T00:00:00Z',
          setup: {} as SessionCreateResponse['setup'],
        } });
      });
    });
  });

  // The screenshot on issue #508: "Start scenario" came back 422, the card
  // said only "VALIDATION_ERROR: Request validation failed", and its own
  // "Copy diagnostics" then answered "Copy failed" — so the reporter could
  // capture neither the cause nor the logs. Both halves are covered here
  // together, because either one alone still strands the player.
  describe('a rejected session create (issue #508)', () => {
    const VALIDATION_422 = {
      ok: false as const,
      error: {
        kind: 'http-error' as const,
        status: 422,
        message:
          'VALIDATION_ERROR: Request validation failed — tts_voice_id: Input should be a valid string',
      },
    };

    beforeEach(() => {
      mockApi.getScenario.mockResolvedValue({ ok: true as const, data: mockScenario });
      mockApi.health.mockResolvedValue({ ok: true as const, data: healthReady });
      mockApi.createSession.mockResolvedValue(VALIDATION_422);
    });

    it('shows which field the backend rejected', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      fireEvent.click(screen.getByRole('button', { name: /start scenario/i }));

      const alert = await screen.findByRole('alert');
      expect(alert).toHaveTextContent('tts_voice_id: Input should be a valid string');
    });

    it('copies the diagnostics report through the desktop shell', async () => {
      // The packaged macOS build has neither web clipboard API: tauri://localhost
      // is not a secure context, so navigator.clipboard is undefined, and WebKit
      // refuses execCommand('copy') once the gesture that started the copy has
      // been outlived by the report's own log-excerpt fetch.
      expect(navigator.clipboard).toBeUndefined();
      const invoke = vi.fn().mockResolvedValue(undefined);
      const win = window as unknown as { __TAURI__?: unknown };
      win.__TAURI__ = { core: { invoke } };
      try {
        renderSetup();
        await waitFor(() => screen.getByText('Behavioral Interview'));
        fireEvent.click(screen.getByRole('button', { name: /start scenario/i }));

        const copyBtn = await screen.findByTestId('copy-diagnostics');
        fireEvent.click(copyBtn);
        await waitFor(() => expect(copyBtn).toHaveTextContent('Copied!'));

        const copied = String((invoke.mock.calls[0][1] as { text: string }).text);
        expect(copied).toContain('status: 422');
        expect(copied).toContain('tts_voice_id: Input should be a valid string');
        expect(copied).toContain('context: ScenarioSetup-Submit');
        // …and the server-side log line for the very request that failed.
        expect(copied).toContain('Request validation failed for POST /api/sessions');
      } finally {
        delete win.__TAURI__;
      }
    });
  });

  describe('runtime readiness panel', () => {
    it('shows all runtime statuses', async () => {
      mockApi.getScenario.mockResolvedValue({ ok: true as const, data: mockScenario });
      mockApi.health.mockResolvedValue({ ok: true as const, data: healthReady });
      renderSetup();
      await waitFor(() => screen.getByTestId('runtime-readiness'));
      expect(screen.getByText(/LLM:/)).toBeInTheDocument();
      expect(screen.getByText(/STT:/)).toBeInTheDocument();
      expect(screen.getByText(/TTS:/)).toBeInTheDocument();
    });

    it('shows network required as No when runtime reports false', async () => {
      mockApi.getScenario.mockResolvedValue({ ok: true as const, data: mockScenario });
      mockApi.health.mockResolvedValue({ ok: true as const, data: healthReady });
      renderSetup();
      await waitFor(() => screen.getByTestId('runtime-readiness'));
      expect(screen.getByText(/network required to play: no/i)).toBeInTheDocument();
    });

    it('shows network required as Yes when runtime reports true', async () => {
      mockApi.getScenario.mockResolvedValue({ ok: true as const, data: mockScenario });
      mockApi.health.mockResolvedValue({ ok: true as const, data: {
        ...healthReady,
        runtime: { ...healthReady.runtime, network_required: true },
      } });
      renderSetup();
      await waitFor(() => screen.getByTestId('runtime-readiness'));
      expect(screen.getByText(/network required to play: yes/i)).toBeInTheDocument();
    });
  });

  describe('privacy', () => {
    beforeEach(() => {
      mockApi.getScenario.mockResolvedValue({ ok: true as const, data: mockScenario });
      mockApi.health.mockResolvedValue({ ok: true as const, data: healthReady });
    });

    it('shows transcript saving toggle explicitly', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      expect(
        screen.getByRole('checkbox', { name: /save transcript locally/i }),
      ).toBeInTheDocument();
    });

    it('shows local-only note when transcript saving is on', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      expect(screen.getByText(/saved to your local data folder only/i)).toBeInTheDocument();
    });

    it('shows not-saved note when transcript saving is off', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      const toggle = screen.getByRole('checkbox', { name: /save transcript locally/i });
      fireEvent.click(toggle);
      await waitFor(() =>
        expect(screen.getByText(/not saved/i)).toBeInTheDocument(),
      );
    });

    it('shows state meters toggle when scenario permits it', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      expect(
        screen.getByRole('checkbox', { name: /show npc state meters/i }),
      ).toBeInTheDocument();
    });

    it('hides state meters toggle and shows note when scenario does not permit it', async () => {
      mockApi.getScenario.mockResolvedValue({ ok: true as const, data: {
        ...mockScenario,
        state_meters_permitted: false,
      } });
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      expect(
        screen.queryByRole('checkbox', { name: /show npc state meters/i }),
      ).not.toBeInTheDocument();
      expect(
        screen.getByText(/state meters are hidden in this scenario/i),
      ).toBeInTheDocument();
    });
  });

  describe('missing runtime (LLM not loaded)', () => {
    const healthNoLlm: HealthResponse = {
      status: 'error',
      version: '0.1.0',
      runtime: {
        llm_ready: false,
        llm_model_name: null,
        stt_ready: false,
        tts_ready: false,
        tts_voice_name: null,
        network_required: false,
      },
    };

    it('shows a missing-runtime block when no LLM model is loaded', async () => {
      mockApi.getScenario.mockResolvedValue({ ok: true as const, data: mockScenario });
      mockApi.health.mockResolvedValue({ ok: true as const, data: healthNoLlm });
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      expect(screen.getByTestId('missing-runtime-block')).toBeInTheDocument();
      expect(screen.getByText(/no llm model is loaded/i)).toBeInTheDocument();
    });

    it('disables the start button when no LLM model is loaded', async () => {
      mockApi.getScenario.mockResolvedValue({ ok: true as const, data: mockScenario });
      mockApi.health.mockResolvedValue({ ok: true as const, data: healthNoLlm });
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      expect(screen.getByRole('button', { name: /start conversation/i })).toBeDisabled();
    });

    it('shows a model manager hint in the missing-runtime block', async () => {
      mockApi.getScenario.mockResolvedValue({ ok: true as const, data: mockScenario });
      mockApi.health.mockResolvedValue({ ok: true as const, data: healthNoLlm });
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      expect(screen.getByTestId('missing-runtime-block')).toHaveTextContent(/model manager/i);
    });

    it('opens the model manager from the missing-runtime hint', async () => {
      // A working control, not prose about Settings: the demo edition hides
      // the model section of Settings (issue #495).
      mockApi.getScenario.mockResolvedValue({ ok: true as const, data: mockScenario });
      mockApi.health.mockResolvedValue({ ok: true as const, data: healthNoLlm });
      const onInstallModel = vi.fn();
      renderSetup({ onInstallModel });
      await waitFor(() => screen.getByText('Behavioral Interview'));
      fireEvent.click(screen.getByTestId('open-model-manager'));
      expect(onInstallModel).toHaveBeenCalledTimes(1);
    });

    it('does not show the missing-runtime block when LLM is ready', async () => {
      mockApi.getScenario.mockResolvedValue({ ok: true as const, data: mockScenario });
      mockApi.health.mockResolvedValue({ ok: true as const, data: healthReady });
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      expect(screen.queryByTestId('missing-runtime-block')).not.toBeInTheDocument();
    });
  });

  describe('back navigation', () => {
    it('calls onBack when the back button is clicked', async () => {
      mockApi.getScenario.mockResolvedValue({ ok: true as const, data: mockScenario });
      mockApi.health.mockResolvedValue({ ok: true as const, data: healthReady });
      const { onBack } = renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      fireEvent.click(screen.getByRole('button', { name: /back to library/i }));
      expect(onBack).toHaveBeenCalled();
    });
  });
  // ── Conversation Brief design (issue #486) ─────────────────────────────────
  // The page is a briefing, not a form: it has to say what the conversation is,
  // make the difficulty choice readable, and keep the start control findable.

  describe('brief hero', () => {
    beforeEach(() => {
      mockApi.getScenario.mockResolvedValue({ ok: true as const, data: mockScenario });
      mockApi.health.mockResolvedValue({ ok: true as const, data: healthReady });
    });

    it('states the facts of the engagement', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      const facts = screen.getByTestId('brief-facts');
      expect(facts).toHaveTextContent('You play');
      expect(facts).toHaveTextContent('Candidate');
      expect(facts).toHaveTextContent('15–20 minutes');
      expect(facts).toHaveTextContent('18 turns');
      expect(facts).toHaveTextContent('PG');
    });

    it('names the screen so the player knows what it is', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      expect(screen.getByText(/conversation brief/i)).toBeInTheDocument();
    });
  });

  describe('difficulty trait meters', () => {
    beforeEach(() => {
      mockApi.getScenario.mockResolvedValue({ ok: true as const, data: mockScenario });
      mockApi.health.mockResolvedValue({ ok: true as const, data: healthReady });
    });

    it('draws the character traits of each level, fill matching the number', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      const warm = document.querySelector('[data-level="warm"]') as HTMLElement;
      expect(within(warm).getByText('Patience')).toBeInTheDocument();
      expect(within(warm).getByText('80')).toBeInTheDocument();
      expect(within(warm).getByText('Disclosure')).toBeInTheDocument();
      expect(within(warm).getByText('70')).toBeInTheDocument();
      const patienceFill = warm.querySelector('.brief-meter-fill') as HTMLElement;
      expect(patienceFill.style.width).toBe('80%');
    });

    // The bar is what tells a sighted player that 80 is high. A screen reader
    // gets no bar, so the meter has to carry the scale — the same way the state
    // meters on the conversation and debrief screens do.
    it('announces each trait against its scale, not as a bare number', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      const warm = document.querySelector('[data-level="warm"]') as HTMLElement;
      expect(
        within(warm).getByRole('meter', { name: 'Patience: 80 out of 100' }),
      ).toHaveAttribute('aria-valuenow', '80');
      expect(
        within(warm).getByRole('meter', { name: 'Time pressure: 20 out of 100' }),
      ).toBeInTheDocument();
      // …and the visible label and number are the meter's own rendering, so
      // they are not read a second time.
      expect(within(warm).getByText('Patience')).toHaveAttribute('aria-hidden', 'true');
      expect(within(warm).getByText('80')).toHaveAttribute('aria-hidden', 'true');
    });

    it('omits meters for a level that declares no traits', async () => {
      mockApi.getScenario.mockResolvedValue({ ok: true as const, data: {
        ...mockScenario,
        difficulty: {
          default: 'standard' as const,
          options: { standard: { label: 'Standard' } },
        },
      } });
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      const standard = document.querySelector('[data-level="standard"]') as HTMLElement;
      expect(standard.querySelector('.brief-meter')).toBeNull();
    });

    it('selects the level when the meters are clicked, not just the label', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      const hard = document.querySelector('[data-level="hard"]') as HTMLElement;
      fireEvent.click(hard.querySelector('.brief-meters') as HTMLElement);
      expect(screen.getByRole('radio', { name: /hard/i })).toBeChecked();
      expect(hard).toHaveClass('is-selected');
    });

    it('marks the chosen level and moves the mark when it changes', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      expect(document.querySelector('[data-level="standard"]')).toHaveClass('is-selected');
      fireEvent.click(screen.getByRole('radio', { name: /hard/i }));
      expect(document.querySelector('[data-level="hard"]')).toHaveClass('is-selected');
      expect(document.querySelector('[data-level="standard"]')).not.toHaveClass('is-selected');
    });
  });

  describe('launch bar', () => {
    beforeEach(() => {
      mockApi.getScenario.mockResolvedValue({ ok: true as const, data: mockScenario });
      mockApi.health.mockResolvedValue({ ok: true as const, data: healthReady });
    });

    it('carries the start control', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      expect(
        within(screen.getByTestId('brief-launch')).getByRole('button', { name: /start conversation/i }),
      ).toBeInTheDocument();
    });

    // The bar is pinned, so Start can be pressed from any scroll position. An
    // error rendered at the end of the page would be off-screen and the press
    // would look like it did nothing — the failure has to be in the bar.
    it('reports a failed start in the bar, beside the button that failed', async () => {
      mockApi.createSession.mockResolvedValue({ ok: false as const, error: { kind: 'http-error' as const, message: 'Core service is not reachable', status: 500 } });
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));

      fireEvent.click(screen.getByRole('button', { name: /start conversation/i }));

      await waitFor(() =>
        expect(within(screen.getByTestId('brief-launch')).getByRole('alert')).toHaveTextContent(
          /Request failed/i,
        ),
      );
      // …and the bar must not still read "ready" directly above that report.
      expect(screen.getByTestId('brief-launch')).toHaveTextContent(/could not start/i);
      expect(screen.getByTestId('brief-launch')).not.toHaveTextContent(/ready to start/i);
    });

    it('reports readiness when nothing blocks the start', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      expect(screen.getByTestId('brief-launch')).toHaveTextContent(/ready to start/i);
    });

    it('summarises what is about to start, and follows the form', async () => {
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      expect(screen.getByTestId('brief-launch-summary')).toHaveTextContent(
        'Standard · English · Push-to-talk · Voice on',
      );

      fireEvent.click(screen.getByRole('radio', { name: /warm-up/i }));
      fireEvent.change(screen.getByRole('combobox', { name: /conversation language/i }), {
        target: { value: 'es' },
      });
      fireEvent.click(screen.getByRole('radio', { name: /text only/i }));
      fireEvent.click(screen.getByRole('checkbox', { name: /npc voice/i }));

      expect(screen.getByTestId('brief-launch-summary')).toHaveTextContent(
        'Warm-up · Spanish · Text · Voice off',
      );
    });

    it('counts what still needs attention instead of starting', async () => {
      mockApi.health.mockResolvedValue({ ok: true as const, data: {
        ...healthReady,
        runtime: { ...healthReady.runtime, llm_ready: false, llm_model_name: null },
      } });
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      expect(screen.getByTestId('brief-launch')).toHaveTextContent('1 item needs attention');

      fireEvent.change(screen.getByRole('textbox', { name: /name to use in this session/i }), {
        target: { value: '' },
      });
      expect(screen.getByTestId('brief-launch')).toHaveTextContent('2 items need attention');
      expect(screen.getByRole('button', { name: /start conversation/i })).toBeDisabled();
    });
  });

  describe('what this practises', () => {
    beforeEach(() => {
      mockApi.health.mockResolvedValue({ ok: true as const, data: healthReady });
    });

    it('lists the dimensions the scenario is scored on', async () => {
      mockApi.getScenario.mockResolvedValue({ ok: true as const, data: {
        ...mockScenario,
        taught_dimensions: ['rapport'],
        tested_dimensions: ['clarity', 'self_awareness'],
      } });
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      const panel = screen.getByTestId('brief-practises');
      expect(within(panel).getByText('clarity')).toBeInTheDocument();
      expect(within(panel).getByText('self awareness')).toBeInTheDocument();
      expect(within(panel).queryByText('rapport')).not.toBeInTheDocument();
    });

    it('falls back to the taught dimensions when nothing is scored', async () => {
      mockApi.getScenario.mockResolvedValue({ ok: true as const, data: {
        ...mockScenario,
        taught_dimensions: ['rapport'],
        tested_dimensions: [],
      } });
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      expect(within(screen.getByTestId('brief-practises')).getByText('rapport')).toBeInTheDocument();
    });

    it('is absent when the scenario declares neither', async () => {
      mockApi.getScenario.mockResolvedValue({ ok: true as const, data: mockScenario });
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      expect(screen.queryByTestId('brief-practises')).not.toBeInTheDocument();
    });
  });

  // The brief carries a lot of new structure — a radiogroup of rows that select
  // as a whole, decorative meters and step numbers hidden from the a11y tree,
  // and a live region in the launch bar. Guard it the way the other screens are
  // guarded in __tests__/accessibility.test.tsx.
  describe('accessibility', () => {
    it('has no axe violations once the brief has loaded', async () => {
      mockApi.getScenario.mockResolvedValue({ ok: true as const, data: {
        ...mockScenario,
        tested_dimensions: ['clarity'],
      } });
      mockApi.health.mockResolvedValue({ ok: true as const, data: healthReady });
      const { container } = render(
        <ScenarioSetupPage
          scenarioId="behavioral_interview"
          onSessionCreated={vi.fn()}
          onBack={vi.fn()}
          onInstallModel={vi.fn()}
        />,
      );
      await waitFor(() => screen.getByText('Behavioral Interview'));
      // Colour contrast is not computable in jsdom — it is checked in the
      // browser pass, as in the shared accessibility suite.
      const results = await axe.run(container, { rules: { 'color-contrast': { enabled: false } } });
      expect(
        results.violations.map((v) => `${v.id}: ${v.nodes[0]?.html ?? ''}`),
      ).toEqual([]);
    });
  });
});
