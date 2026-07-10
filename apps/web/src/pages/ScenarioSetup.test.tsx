import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { ScenarioSetupPage } from './ScenarioSetup';
import type { ScenarioInfo, HealthResponse, SessionCreateResponse } from '@convsim/shared';

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
  mockApi.listVoices.mockResolvedValue(STUB_VOICES);
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
      mockApi.getScenario.mockResolvedValue(mockScenario);
      mockApi.health.mockResolvedValue(healthReady);
      renderSetup();
      await waitFor(() =>
        expect(screen.getByText('Behavioral Interview')).toBeInTheDocument(),
      );
      expect(screen.getByTestId('setup-page')).toBeInTheDocument();
      expect(screen.getByText('Job Interview Basics')).toBeInTheDocument();
    });

    it('shows load error when API fails', async () => {
      mockApi.getScenario.mockRejectedValue(new Error('Network error'));
      mockApi.health.mockResolvedValue(healthReady);
      renderSetup();
      await waitFor(() =>
        expect(screen.getByText(/failed to load scenario/i)).toBeInTheDocument(),
      );
    });

    it('renders the form in text-only mode when health endpoint fails', async () => {
      mockApi.getScenario.mockResolvedValue(mockScenario);
      mockApi.health.mockRejectedValue(new Error('Health unavailable'));
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
      mockApi.getScenario.mockResolvedValue(mockScenario);
      mockApi.health.mockResolvedValue(healthReady);
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
      mockApi.getScenario.mockResolvedValue({ ...mockScenario, voice_supported: false });
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      const ttsCheckbox = screen.getByRole('checkbox', { name: /npc voice/i });
      expect(ttsCheckbox).not.toBeChecked();
    });

    it('shows a note when scenario is text-only but TTS is technically available', async () => {
      mockApi.getScenario.mockResolvedValue({ ...mockScenario, voice_supported: false });
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
      mockApi.getScenario.mockResolvedValue(mockScenario);
      mockApi.health.mockResolvedValue(healthReady);
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
      mockApi.getScenario.mockResolvedValue(mockScenario);
      mockApi.health.mockResolvedValue(healthTextOnly);
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
      mockApi.getScenario.mockResolvedValue(mockScenario);
      mockApi.health.mockResolvedValue(healthReady);
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      const nameInput = screen.getByRole('textbox', {
        name: /name to use in this session/i,
      });
      fireEvent.change(nameInput, { target: { value: '' } });
      const submitBtn = screen.getByRole('button', { name: /start scenario/i });
      expect(submitBtn).toBeDisabled();
    });
  });

  describe('voice selection', () => {
    beforeEach(() => {
      mockApi.getScenario.mockResolvedValue(mockScenario);
      mockApi.health.mockResolvedValue(healthReady);
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
      mockApi.getScenario.mockResolvedValue(mockScenario);
      mockApi.health.mockResolvedValue(healthReady);
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
      expect(screen.getByRole('button', { name: /start scenario/i })).toBeDisabled();
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
      expect(screen.getByRole('button', { name: /start scenario/i })).toBeDisabled();
    });
  });

  describe('session creation', () => {
    beforeEach(() => {
      mockApi.getScenario.mockResolvedValue(mockScenario);
      mockApi.health.mockResolvedValue(healthReady);
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
      mockApi.createSession.mockResolvedValue(mockSession);

      const { onSessionCreated } = renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));

      const submitBtn = screen.getByRole('button', { name: /start scenario/i });
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
      mockApi.createSession.mockResolvedValue({
        session_id: 'sess-456',
        scenario_id: 'behavioral_interview',
        state: 'NotStarted',
        created_at: '2026-06-30T00:00:00Z',
        setup: {} as SessionCreateResponse['setup'],
      });

      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));

      const seedInput = screen.getByRole('spinbutton', {
        name: /variation seed value/i,
      });
      fireEvent.change(seedInput, { target: { value: '9999' } });

      const submitBtn = screen.getByRole('button', { name: /start scenario/i });
      fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(mockApi.createSession).toHaveBeenCalledWith(
          expect.objectContaining({ seed: 9999 }),
        );
      });
    });

    it('shows error message when createSession fails', async () => {
      mockApi.createSession.mockRejectedValue(new Error('Server error'));

      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));

      const submitBtn = screen.getByRole('button', { name: /start scenario/i });
      fireEvent.click(submitBtn);

      await waitFor(() =>
        expect(screen.getByRole('alert')).toHaveTextContent(/Server error/),
      );
    });

    it('shows human-readable message not raw JSON when error has a message field', async () => {
      mockApi.createSession.mockRejectedValue(
        new Error('Unknown scenario_id: behavioral_interview'),
      );

      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));

      const submitBtn = screen.getByRole('button', { name: /start scenario/i });
      fireEvent.click(submitBtn);

      await waitFor(() => {
        const alert = screen.getByRole('alert');
        expect(alert).toHaveTextContent('Unknown scenario_id: behavioral_interview');
        expect(alert).not.toHaveTextContent('"statusCode"');
      });
    });

    it('disables submit button while submitting', async () => {
      let resolveSession!: (v: SessionCreateResponse) => void;
      mockApi.createSession.mockReturnValue(
        new Promise<SessionCreateResponse>((resolve) => {
          resolveSession = resolve;
        }),
      );

      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));

      const submitBtn = screen.getByRole('button', { name: /start scenario/i });
      fireEvent.click(submitBtn);

      await waitFor(() =>
        expect(screen.getByRole('button', { name: /starting/i })).toBeDisabled(),
      );

      await act(async () => {
        resolveSession({
          session_id: 'sess-789',
          scenario_id: 'behavioral_interview',
          state: 'NotStarted',
          created_at: '2026-06-30T00:00:00Z',
          setup: {} as SessionCreateResponse['setup'],
        });
      });
    });
  });

  describe('runtime readiness panel', () => {
    it('shows all runtime statuses', async () => {
      mockApi.getScenario.mockResolvedValue(mockScenario);
      mockApi.health.mockResolvedValue(healthReady);
      renderSetup();
      await waitFor(() => screen.getByTestId('runtime-readiness'));
      expect(screen.getByText(/LLM:/)).toBeInTheDocument();
      expect(screen.getByText(/STT:/)).toBeInTheDocument();
      expect(screen.getByText(/TTS:/)).toBeInTheDocument();
    });

    it('shows network required as No when runtime reports false', async () => {
      mockApi.getScenario.mockResolvedValue(mockScenario);
      mockApi.health.mockResolvedValue(healthReady);
      renderSetup();
      await waitFor(() => screen.getByTestId('runtime-readiness'));
      expect(screen.getByText(/network required to play: no/i)).toBeInTheDocument();
    });

    it('shows network required as Yes when runtime reports true', async () => {
      mockApi.getScenario.mockResolvedValue(mockScenario);
      mockApi.health.mockResolvedValue({
        ...healthReady,
        runtime: { ...healthReady.runtime, network_required: true },
      });
      renderSetup();
      await waitFor(() => screen.getByTestId('runtime-readiness'));
      expect(screen.getByText(/network required to play: yes/i)).toBeInTheDocument();
    });
  });

  describe('privacy', () => {
    beforeEach(() => {
      mockApi.getScenario.mockResolvedValue(mockScenario);
      mockApi.health.mockResolvedValue(healthReady);
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
      mockApi.getScenario.mockResolvedValue({
        ...mockScenario,
        state_meters_permitted: false,
      });
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
      mockApi.getScenario.mockResolvedValue(mockScenario);
      mockApi.health.mockResolvedValue(healthNoLlm);
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      expect(screen.getByTestId('missing-runtime-block')).toBeInTheDocument();
      expect(screen.getByText(/no llm model is loaded/i)).toBeInTheDocument();
    });

    it('disables the start button when no LLM model is loaded', async () => {
      mockApi.getScenario.mockResolvedValue(mockScenario);
      mockApi.health.mockResolvedValue(healthNoLlm);
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      expect(screen.getByRole('button', { name: /start scenario/i })).toBeDisabled();
    });

    it('shows a model manager hint in the missing-runtime block', async () => {
      mockApi.getScenario.mockResolvedValue(mockScenario);
      mockApi.health.mockResolvedValue(healthNoLlm);
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      expect(screen.getByTestId('missing-runtime-block')).toHaveTextContent(/model manager/i);
    });

    it('does not show the missing-runtime block when LLM is ready', async () => {
      mockApi.getScenario.mockResolvedValue(mockScenario);
      mockApi.health.mockResolvedValue(healthReady);
      renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      expect(screen.queryByTestId('missing-runtime-block')).not.toBeInTheDocument();
    });
  });

  describe('back navigation', () => {
    it('calls onBack when the back button is clicked', async () => {
      mockApi.getScenario.mockResolvedValue(mockScenario);
      mockApi.health.mockResolvedValue(healthReady);
      const { onBack } = renderSetup();
      await waitFor(() => screen.getByText('Behavioral Interview'));
      fireEvent.click(screen.getByRole('button', { name: /back to library/i }));
      expect(onBack).toHaveBeenCalled();
    });
  });
});
