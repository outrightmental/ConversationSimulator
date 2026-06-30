import { useState, useEffect, useCallback } from 'react';
import type {
  ScenarioInfo,
  ScenarioDifficulty,
  SetupFormValues,
  InputMode,
  RuntimeReadiness,
  SessionCreateResponse,
} from '@convsim/shared';
import { validateSetup, randomSeed } from '@convsim/shared';
import { api } from '../api/client';

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
  const [loadError, setLoadError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const [form, setForm] = useState<SetupFormValues>({
    difficulty: 'normal',
    player_role_name: '',
    language: 'en',
    input_mode: 'text-only',
    tts_enabled: false,
    show_state_meters: false,
    save_transcript: true,
    seed: null,
  });

  useEffect(() => {
    let cancelled = false;

    Promise.all([api.getScenario(scenarioId), api.health()]).then(
      ([scenarioData, health]) => {
        if (cancelled) return;
        setScenario(scenarioData);
        setRuntime(health.runtime);
        setForm((prev) => ({
          ...prev,
          difficulty: scenarioData.difficulty.default,
          player_role_name: scenarioData.player_role.label,
          language: scenarioData.supported_languages[0] ?? 'en',
          tts_enabled: health.runtime.tts_ready,
          input_mode: health.runtime.stt_ready ? 'push-to-talk' : 'text-only',
        }));
      },
      (err: unknown) => {
        if (!cancelled) setLoadError(String(err));
      },
    );

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
      try {
        const session = await api.createSession({
          scenario_id: scenarioId,
          ...form,
        });
        onSessionCreated(session);
      } catch (err: unknown) {
        setSubmitError(String(err));
      } finally {
        setSubmitting(false);
      }
    },
    [form, scenarioId, scenario, validationResult.valid, onSessionCreated],
  );

  if (loadError) {
    return (
      <div className="setup-page" data-testid="setup-page">
        <div className="setup-error" role="alert">
          <h2>Failed to load scenario</h2>
          <p>{loadError}</p>
          <button onClick={onBack}>Go back</button>
        </div>
      </div>
    );
  }

  if (scenario == null) {
    return (
      <div className="setup-page" data-testid="setup-page">
        <div className="setup-loading" aria-live="polite" aria-busy="true">
          Loading scenario…
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
          <section className="setup-section" aria-labelledby="difficulty-heading">
            <h2 id="difficulty-heading" className="setup-section-title">
              Difficulty
            </h2>
            <div className="setup-radio-group" role="radiogroup" aria-label="Difficulty">
              {availableDifficulties.map((level) => (
                <label key={level} className="setup-radio-label">
                  <input
                    type="radio"
                    name="difficulty"
                    value={level}
                    checked={form.difficulty === level}
                    onChange={() => setField('difficulty', level)}
                  />
                  <span className="setup-radio-text">
                    {level.charAt(0).toUpperCase() + level.slice(1)}
                  </span>
                </label>
              ))}
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
                    setField('seed', v === '' ? null : parseInt(v, 10));
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
              {submitError}
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
                <span className={`setup-status-dot ${runtime.llm_ready ? 'ready' : 'not-ready'}`} />
                <span>
                  LLM:{' '}
                  {runtime.llm_ready
                    ? runtime.llm_model_name ?? 'ready'
                    : 'not loaded'}
                </span>
              </li>
              <li>
                <span className={`setup-status-dot ${runtime.stt_ready ? 'ready' : 'not-ready'}`} />
                <span>STT: {runtime.stt_ready ? 'ready' : 'not loaded'}</span>
              </li>
              <li>
                <span className={`setup-status-dot ${runtime.tts_ready ? 'ready' : 'not-ready'}`} />
                <span>
                  TTS:{' '}
                  {runtime.tts_ready
                    ? runtime.tts_voice_name ?? 'ready'
                    : 'not loaded'}
                </span>
              </li>
              <li>
                <span className={`setup-status-dot ${runtime.network_required ? 'not-ready' : 'ready'}`} />
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
