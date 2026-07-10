import { useState, useEffect, useCallback } from 'react';
import type {
  ScenarioInfo,
  ScenarioDifficulty,
  DifficultyOption,
  SetupFormValues,
  InputMode,
  RuntimeReadiness,
  SessionCreateResponse,
  VoiceInfo,
} from '@convsim/shared';
import { validateSetup, randomSeed } from '@convsim/shared';
import { api } from '../api/client';
import type { ApiError } from '../api/errors';
import { ApiErrorView } from '../components/ApiErrorView';
import { readPrivacyPref, PRIVACY_KEYS } from '../privacyPrefs';

const DIFFICULTY_LABELS: Record<ScenarioDifficulty, string> = {
  warm:        'Warm-up',
  standard:    'Standard',
  hard:        'Hard',
  adversarial: 'Adversarial',
};

const DIFFICULTY_DESCRIPTIONS: Record<ScenarioDifficulty, string> = {
  warm:        'The NPC is patient and forthcoming — ideal for first attempts or building confidence.',
  standard:    'Balanced challenge with realistic NPC behaviour — the author\'s recommended starting point.',
  hard:        'The NPC is terse, reactive, and discloses little; expect rapid state swings.',
  adversarial: 'Maximum challenge: very low patience, high state volatility, almost no disclosure, strong time pressure.',
};

function difficultyDescription(level: ScenarioDifficulty, option: DifficultyOption | undefined): string {
  return option?.description ?? DIFFICULTY_DESCRIPTIONS[level] ?? level;
}

function difficultyLabel(level: ScenarioDifficulty, option: DifficultyOption | undefined): string {
  return option?.label ?? DIFFICULTY_LABELS[level] ?? level.charAt(0).toUpperCase() + level.slice(1);
}

const LANGUAGE_LABELS: Record<string, string> = {
  en: 'English',
  es: 'Spanish',
  fr: 'French',
  ja: 'Japanese',
  de: 'German',
  zh: 'Chinese',
  pt: 'Portuguese',
  it: 'Italian',
  ko: 'Korean',
  nl: 'Dutch',
};

function languageLabel(code: string): string {
  return LANGUAGE_LABELS[code] ?? code;
}

interface Props {
  scenarioId: string;
  onSessionCreated: (session: SessionCreateResponse) => void;
  onBack: () => void;
}

export function ScenarioSetupPage({ scenarioId, onSessionCreated, onBack }: Props) {
  const [scenario, setScenario] = useState<ScenarioInfo | null>(null);
  const [runtime, setRuntime] = useState<RuntimeReadiness>({
    llm_ready: false,
    llm_model_name: null,
    stt_ready: false,
    tts_ready: false,
    tts_voice_name: null,
    network_required: false,
  });
  const [voices, setVoices] = useState<VoiceInfo[]>([]);
  const [loadError, setLoadError] = useState<ApiError | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<ApiError | null>(null);

  const [form, setForm] = useState<SetupFormValues>({
    difficulty: 'standard',
    player_role_name: '',
    language: 'en',
    input_mode: 'text-only',
    tts_enabled: false,
    voice_id: localStorage.getItem('convsim.voice.preferredVoiceId') ?? null,
    show_state_meters: false,
    save_transcript: readPrivacyPref(PRIVACY_KEYS.saveTranscripts, true),
    seed: null,
  });

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      const [scenarioR, healthR, voicesR] = await Promise.all([
        api.getScenario(scenarioId),
        api.health(),
        api.listVoices(),
      ])
      if (cancelled) return
      if (!scenarioR.ok) { setLoadError(scenarioR.error); return }
      const scenarioData = scenarioR.data
      const voiceList = voicesR.ok ? voicesR.data.voices : []
      const rt = healthR.ok ? (healthR.data.runtime ?? {
        llm_ready: false,
        llm_model_name: null,
        stt_ready: false,
        tts_ready: false,
        tts_voice_name: null,
        network_required: false,
      }) : {
        llm_ready: false,
        llm_model_name: null,
        stt_ready: false,
        tts_ready: false,
        tts_voice_name: null,
        network_required: false,
      }
      setScenario(scenarioData)
      setVoices(voiceList)
      setRuntime(rt)
      setForm((prev) => {
        // Pick a default voice: honour stored preference if valid, else first available.
        const storedVoiceId = localStorage.getItem('convsim.voice.preferredVoiceId')
        const defaultVoiceId =
          storedVoiceId && voiceList.some((v) => v.voice_id === storedVoiceId)
            ? storedVoiceId
            : voiceList[0]?.voice_id ?? null
        return {
          ...prev,
          difficulty: scenarioData.difficulty.default,
          player_role_name: scenarioData.player_role.label,
          language: scenarioData.supported_languages[0] ?? 'en',
          tts_enabled: rt.tts_ready && (scenarioData.voice_supported !== false),
          voice_id: prev.voice_id && voiceList.some((v) => v.voice_id === prev.voice_id)
            ? prev.voice_id
            : defaultVoiceId,
          input_mode: rt.stt_ready ? 'push-to-talk' : 'text-only',
          show_state_meters: scenarioData.state_meters_permitted ? prev.show_state_meters : false,
        }
      })
    })();

    return () => {
      cancelled = true;
    };
  }, [scenarioId]);

  const setField = useCallback(
    <K extends keyof SetupFormValues>(key: K, value: SetupFormValues[K]) => {
      setForm((prev) => ({ ...prev, [key]: value }));
    },
    [],
  );

  const handleRandomizeSeed = useCallback(() => {
    setField('seed', randomSeed());
  }, [setField]);

  const handleClearSeed = useCallback(() => {
    setField('seed', null);
  }, [setField]);

  const validationResult =
    scenario != null
      ? validateSetup(form, runtime, scenario.state_meters_permitted)
      : { valid: false, errors: [] };

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!validationResult.valid || scenario == null) return;

      setSubmitting(true);
      setSubmitError(null);
      // `voice_id` is the UI form field; the backend expects `tts_voice_id`
      // (a non-null approved voice id). Omit it when no voice is selected so
      // the backend applies its default rather than rejecting a null value.
      const { voice_id, ...rest } = form;
      const r = await api.createSession({
        scenario_id: scenarioId,
        ...rest,
        ...(voice_id ? { tts_voice_id: voice_id } : {}),
      });
      if (r.ok) {
        onSessionCreated(r.data);
      } else {
        setSubmitError(r.error);
      }
      setSubmitting(false);
    },
    [form, scenarioId, scenario, validationResult.valid, onSessionCreated],
  );

  if (loadError) {
    return (
      <div className="setup-page" data-testid="setup-page">
        <div className="setup-error">
          <h2>Failed to load scenario</h2>
          <ApiErrorView error={loadError} context="ScenarioSetup" />
          <button onClick={onBack} style={{ marginTop: '0.75rem' }}>Go back</button>
        </div>
      </div>
    );
  }

  if (scenario == null) {
    return (
      <div className="setup-page" data-testid="setup-page">
        <div className="setup-loading" aria-live="polite" aria-busy="true">
          Loading scenario {scenarioId}…
        </div>
      </div>
    );
  }

  const availableDifficulties = Object.keys(
    scenario.difficulty.options,
  ) as ScenarioDifficulty[];

  const validationErrorMap = Object.fromEntries(
    validationResult.errors.map((e) => [e.field, e.message]),
  );

  const formLevelErrors = validationResult.errors.filter((e) => e.field === '_form');

  return (
    <div className="setup-page" data-testid="setup-page">
      <header className="setup-header">
        <button className="setup-back-btn" onClick={onBack} aria-label="Back to library">
          ← Back
        </button>
        <div className="setup-title-group">
          <span className="setup-pack-name">{scenario.pack_name}</span>
          <h1 className="setup-scenario-title">{scenario.title}</h1>
          <p className="setup-scenario-summary">{scenario.summary}</p>
        </div>
      </header>

      <div className="setup-layout">
        <form className="setup-form" onSubmit={handleSubmit} noValidate>
          {formLevelErrors.length > 0 && (
            <div
              className="setup-missing-runtime"
              role="alert"
              data-testid="missing-runtime-block"
            >
              {formLevelErrors.map((e, i) => (
                <p key={i} className="setup-missing-runtime-message">{e.message}</p>
              ))}
              <p className="setup-missing-runtime-hint">
                Go to <strong>Settings → Model Manager</strong> to install a model, then return
                here to launch your scenario.
              </p>
            </div>
          )}

          <section className="setup-section" aria-labelledby="difficulty-heading">
            <h2 id="difficulty-heading" className="setup-section-title">
              Difficulty
            </h2>
            <div className="setup-radio-group" role="radiogroup" aria-label="Difficulty">
              {availableDifficulties.map((level) => {
                const option = scenario.difficulty.options[level];
                return (
                  <label key={level} className="setup-radio-label">
                    <input
                      type="radio"
                      name="difficulty"
                      value={level}
                      checked={form.difficulty === level}
                      onChange={() => setField('difficulty', level)}
                    />
                    <span className="setup-radio-text">
                      <span className="setup-difficulty-name">
                        {difficultyLabel(level, option)}
                        {level === scenario.difficulty.default && (
                          <span className="setup-difficulty-recommended"> (recommended)</span>
                        )}
                      </span>
                      <span className="setup-difficulty-description">
                        {difficultyDescription(level, option)}
                      </span>
                    </span>
                  </label>
                );
              })}
            </div>
          </section>

          <section className="setup-section" aria-labelledby="player-heading">
            <h2 id="player-heading" className="setup-section-title">
              Your role
            </h2>
            <p className="setup-role-brief">{scenario.player_role.brief}</p>
            <label className="setup-field">
              <span className="setup-label">Name to use in this session</span>
              <input
                type="text"
                className="setup-input"
                value={form.player_role_name}
                onChange={(e) => setField('player_role_name', e.target.value)}
                aria-required="true"
                aria-invalid={!!validationErrorMap['player_role_name']}
                aria-describedby={
                  validationErrorMap['player_role_name']
                    ? 'player-role-error'
                    : undefined
                }
              />
              {validationErrorMap['player_role_name'] && (
                <span id="player-role-error" className="setup-field-error" role="alert">
                  {validationErrorMap['player_role_name']}
                </span>
              )}
            </label>
          </section>

          <section className="setup-section" aria-labelledby="language-heading">
            <h2 id="language-heading" className="setup-section-title">
              Language
            </h2>
            <label className="setup-field">
              <span className="setup-label">Conversation language</span>
              <select
                className="setup-select"
                value={form.language}
                onChange={(e) => setField('language', e.target.value)}
              >
                {scenario.supported_languages.map((code) => (
                  <option key={code} value={code}>
                    {languageLabel(code)}
                  </option>
                ))}
              </select>
            </label>
          </section>

          <section className="setup-section" aria-labelledby="input-heading">
            <h2 id="input-heading" className="setup-section-title">
              Input mode
            </h2>
            <div className="setup-radio-group" role="radiogroup" aria-label="Input mode">
              {(
                [
                  ['text-only', 'Text only', true],
                  ['push-to-talk', 'Push-to-talk voice', runtime.stt_ready],
                  ['hands-free', 'Hands-free voice (VAD)', runtime.stt_ready],
                ] as [InputMode, string, boolean][]
              ).map(([value, label, available]) => (
                <label
                  key={value}
                  className={`setup-radio-label ${!available ? 'setup-radio-disabled' : ''}`}
                >
                  <input
                    type="radio"
                    name="input_mode"
                    value={value}
                    checked={form.input_mode === value}
                    disabled={!available}
                    onChange={() => setField('input_mode', value)}
                  />
                  <span className="setup-radio-text">
                    {label}
                    {!available && value !== 'text-only' && (
                      <span className="setup-unavailable-badge"> (STT not loaded)</span>
                    )}
                  </span>
                </label>
              ))}
            </div>
            {validationErrorMap['input_mode'] && (
              <span className="setup-field-error" role="alert">
                {validationErrorMap['input_mode']}
              </span>
            )}
          </section>

          <section className="setup-section" aria-labelledby="audio-heading">
            <h2 id="audio-heading" className="setup-section-title">
              Audio output
            </h2>
            <label className="setup-toggle-label">
              <input
                type="checkbox"
                checked={form.tts_enabled}
                disabled={!runtime.tts_ready}
                onChange={(e) => setField('tts_enabled', e.target.checked)}
                aria-describedby={!runtime.tts_ready ? 'tts-status' : undefined}
              />
              <span className="setup-toggle-text">
                NPC voice (TTS)
                {runtime.tts_ready && runtime.tts_voice_name && (
                  <span className="setup-badge-ready"> {runtime.tts_voice_name}</span>
                )}
                {!runtime.tts_ready && (
                  <span className="setup-badge-unavailable"> — not loaded</span>
                )}
              </span>
            </label>
            {validationErrorMap['tts_enabled'] && (
              <span className="setup-field-error" role="alert">
                {validationErrorMap['tts_enabled']}
              </span>
            )}
            {!runtime.tts_ready && (
              <p className="setup-fallback-note" id="tts-status">
                Text-only is always available. Install a TTS model to enable voice output.
              </p>
            )}
            {runtime.tts_ready && scenario != null && !scenario.voice_supported && (
              <p className="setup-fallback-note">
                This scenario is designed for text — TTS can still be enabled but the script
                was not written with voice in mind.
              </p>
            )}
            {form.tts_enabled && voices.length > 0 && (
              <label className="setup-field" style={{ marginTop: '0.75rem' }}>
                <span className="setup-label">NPC voice</span>
                <select
                  className="setup-select"
                  value={form.voice_id ?? ''}
                  onChange={(e) => setField('voice_id', e.target.value || null)}
                  aria-label="NPC voice selection"
                >
                  {voices.map((v) => (
                    <option key={v.voice_id} value={v.voice_id}>
                      {v.display_name}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </section>

          <section className="setup-section" aria-labelledby="privacy-heading">
            <h2 id="privacy-heading" className="setup-section-title">
              Privacy options
            </h2>
            <label className="setup-toggle-label">
              <input
                type="checkbox"
                checked={form.save_transcript}
                onChange={(e) => setField('save_transcript', e.target.checked)}
              />
              <span className="setup-toggle-text">
                Save transcript locally
                <span className="setup-privacy-note">
                  {form.save_transcript
                    ? ' — saved to your local data folder only'
                    : ' — not saved'}
                </span>
              </span>
            </label>

            {scenario.state_meters_permitted && (
              <label className="setup-toggle-label">
                <input
                  type="checkbox"
                  checked={form.show_state_meters}
                  onChange={(e) => setField('show_state_meters', e.target.checked)}
                />
                <span className="setup-toggle-text">Show NPC state meters during conversation</span>
              </label>
            )}
            {!scenario.state_meters_permitted && (
              <p className="setup-note">
                State meters are hidden in this scenario to preserve realism.
              </p>
            )}
          </section>

          <section className="setup-section" aria-labelledby="seed-heading">
            <h2 id="seed-heading" className="setup-section-title">
              Variation seed
            </h2>
            <p className="setup-note">
              The seed controls scenario randomization. Use the same seed to replay an
              identical variation, or randomize for a new experience.
            </p>
            <div className="setup-seed-row">
              <label className="setup-field setup-seed-field">
                <span className="setup-label">Seed</span>
                <input
                  type="number"
                  className="setup-input setup-seed-input"
                  value={form.seed ?? ''}
                  placeholder="Auto"
                  min={0}
                  max={2147483647}
                  step={1}
                  onChange={(e) => {
                    const v = e.target.value;
                    const parsed = Number(v);
                    setField('seed', v === '' || isNaN(parsed) ? null : parsed);
                  }}
                  aria-label="Variation seed value"
                  aria-invalid={!!validationErrorMap['seed']}
                  aria-describedby={validationErrorMap['seed'] ? 'seed-error' : undefined}
                />
              </label>
              <button type="button" className="setup-btn-secondary" onClick={handleRandomizeSeed}>
                Randomize
              </button>
              {form.seed !== null && (
                <button type="button" className="setup-btn-ghost" onClick={handleClearSeed}>
                  Auto
                </button>
              )}
            </div>
            {validationErrorMap['seed'] && (
              <span id="seed-error" className="setup-field-error" role="alert">
                {validationErrorMap['seed']}
              </span>
            )}
          </section>

          {submitError && (
            <div className="setup-submit-error" role="alert">
              <ApiErrorView error={submitError} compact context="ScenarioSetup-Submit" />
            </div>
          )}

          <div className="setup-actions">
            <button
              type="submit"
              className="setup-btn-primary"
              disabled={!validationResult.valid || submitting}
              aria-busy={submitting}
            >
              {submitting ? 'Starting…' : 'Start scenario'}
            </button>
          </div>
        </form>

        <aside className="setup-sidebar" aria-label="Scenario information">
          <div className="setup-info-card" data-testid="runtime-readiness">
            <h3 className="setup-info-title">Runtime readiness</h3>
            <ul className="setup-info-list">
              <li>
                <span aria-hidden="true" className={`setup-status-dot ${runtime.llm_ready ? 'ready' : 'not-ready'}`} />
                <span>
                  LLM:{' '}
                  {runtime.llm_ready
                    ? runtime.llm_model_name ?? 'ready'
                    : 'not loaded'}
                </span>
              </li>
              <li>
                <span aria-hidden="true" className={`setup-status-dot ${runtime.stt_ready ? 'ready' : 'not-ready'}`} />
                <span>
                  STT: {runtime.stt_ready ? 'ready' : 'not loaded — voice input unavailable'}
                </span>
              </li>
              <li>
                <span aria-hidden="true" className={`setup-status-dot ${runtime.tts_ready ? 'ready' : 'not-ready'}`} />
                <span>
                  TTS:{' '}
                  {runtime.tts_ready
                    ? runtime.tts_voice_name ?? 'ready'
                    : 'not loaded — text-only available'}
                </span>
              </li>
              <li>
                <span aria-hidden="true" className={`setup-status-dot ${runtime.stt_ready ? 'ready' : 'not-ready'}`} />
                <span>
                  VAD: {runtime.stt_ready ? 'available' : 'requires STT'}
                </span>
              </li>
              <li>
                <span aria-hidden="true" className={`setup-status-dot ${runtime.network_required ? 'not-ready' : 'ready'}`} />
                <span>Network required to play: {runtime.network_required ? 'Yes' : 'No'}</span>
              </li>
            </ul>
          </div>

          <div className="setup-info-card">
            <h3 className="setup-info-title">Scenario details</h3>
            <dl className="setup-info-dl">
              <dt>Content rating</dt>
              <dd>{scenario.content_rating}</dd>
              <dt>Estimated length</dt>
              <dd>{scenario.estimated_length_label}</dd>
              <dt>Voice support</dt>
              <dd>{scenario.voice_supported ? 'Yes' : 'Text only'}</dd>
            </dl>
          </div>

          <div className="setup-info-card">
            <h3 className="setup-info-title">Safety summary</h3>
            <p className="setup-safety-text">{scenario.safety_summary}</p>
          </div>
        </aside>
      </div>
    </div>
  );
}
