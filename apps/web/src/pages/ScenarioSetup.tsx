// SPDX-License-Identifier: Apache-2.0
//
// The Conversation Brief: the screen between choosing a scenario and talking to
// the character. Redesigned in issue #486 as a briefing, not a settings form —
// the page used to be a flat stack of unstyled fieldsets with the start button
// stranded at the bottom, and players could not find it.
//
// Issue #500 took it the rest of the way to a preflight screen: the brief has
// to say, without being read, "I am about to start a conversation, and this is
// what I am trying to achieve". So the page is three tiers of weight, loudest
// first (styles in ./ScenarioSetup.css):
//
//   1. THE MISSION — a hero carrying pack, title and situation beside the
//      objective: the scenario's player-visible goals, numbered, in the
//      brightest panel on the screen. Under them, the facts of the engagement
//      (role, length, turns, rating, voice) read as instruments.
//   2. THE CHOICES — two cards for the two decisions that change the
//      conversation: the character's posture (difficulty, with its traits
//      drawn as meters) and who the player is in it.
//   3. THE SETUP — one quiet card grouping the five mechanical settings
//      (input, audio, language, privacy, seed). They are grouped and demoted,
//      never hidden: every control is still on the screen and still one Tab
//      or one D-pad press away.
//
// Beside them an instrument panel keeps the runtime checks on screen, and a
// launch bar pinned to the bottom of the viewport carries the one primary
// action, what it is about to start, and whether it can.
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
import { languageLabel } from '../lib/languageLabel';
import './ScenarioSetup.css';

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

/**
 * The difficulty traits, drawn as meters on each level card. Emerald traits
 * describe how the character gives; amber traits are what the scenario pushes
 * at the player (docs/brand.md: emerald is "them", amber is "the moment").
 */
type TraitKey = 'patience' | 'disclosure' | 'volatility' | 'time_pressure';

const TRAIT_METERS: ReadonlyArray<{ key: TraitKey; label: string; pressure: boolean }> = [
  { key: 'patience',      label: 'Patience',      pressure: false },
  { key: 'disclosure',    label: 'Disclosure',    pressure: false },
  { key: 'volatility',    label: 'Volatility',    pressure: true },
  { key: 'time_pressure', label: 'Time pressure', pressure: true },
];

/** Short forms for the launch bar, where the full radio labels are too long. */
const INPUT_MODE_SUMMARY: Record<InputMode, string> = {
  'text-only':    'Text',
  'push-to-talk': 'Push-to-talk',
  'hands-free':   'Hands-free',
};

function difficultyDescription(level: ScenarioDifficulty, option: DifficultyOption | undefined): string {
  return option?.description ?? DIFFICULTY_DESCRIPTIONS[level] ?? level;
}

function difficultyLabel(level: ScenarioDifficulty, option: DifficultyOption | undefined): string {
  return option?.label ?? DIFFICULTY_LABELS[level] ?? level.charAt(0).toUpperCase() + level.slice(1);
}

/**
 * Trait meters for one difficulty level. Rendered as a sibling of the option's
 * <label> rather than inside it: a list is not phrasing content, and keeping
 * the numbers out of the radio's accessible name keeps that name short.
 *
 * Each bar is a `role="meter"` carrying the 0–100 scale, as the state meters on
 * the conversation, debrief and workbench screens already are. The bar is what
 * tells a sighted player that 80 is high; without the scale on the meter, a
 * screen reader would read a bare "Patience 80" and lose that. The visible
 * label and number are the meter's own rendering, so they are hidden from the
 * tree to keep each row from being read twice.
 */
function TraitMeters({ option }: { option: DifficultyOption | undefined }) {
  const rows = TRAIT_METERS.filter(({ key }) => typeof option?.[key] === 'number');
  if (option == null || rows.length === 0) return null;
  return (
    <ul className="brief-meters">
      {rows.map(({ key, label, pressure }) => {
        const value = option[key] as number;
        return (
          <li key={key} className={`brief-meter${pressure ? ' is-pressure' : ''}`}>
            <span className="brief-meter-label" aria-hidden="true">{label}</span>
            <span
              className="brief-meter-track"
              role="meter"
              aria-label={`${label}: ${value} out of 100`}
              aria-valuenow={value}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <span
                aria-hidden="true"
                className="brief-meter-fill"
                style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
              />
            </span>
            <span className="brief-meter-value" aria-hidden="true">{value}</span>
          </li>
        );
      })}
    </ul>
  );
}

interface Props {
  scenarioId: string;
  onSessionCreated: (session: SessionCreateResponse) => void;
  onBack: () => void;
  /**
   * Opens the model manager. Wired by the screen wrapper; when absent the
   * missing-runtime hint is plain text. A callback rather than a <Link> keeps
   * this page router-agnostic (it is rendered and tested without one).
   */
  onInstallModel?: () => void;
}

export function ScenarioSetupPage({ scenarioId, onSessionCreated, onBack, onInstallModel }: Props) {
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
          difficulty: scenarioData.difficulty?.default ?? 'standard',
          player_role_name: scenarioData.player_role?.label ?? '',
          language: scenarioData.supported_languages?.[0] ?? 'en',
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
      <div className="brief" data-testid="setup-page">
        <div className="brief-error">
          <h2>Failed to load scenario</h2>
          <ApiErrorView error={loadError} context="ScenarioSetup" />
          <button type="button" className="brief-btn-secondary" onClick={onBack} style={{ marginTop: '0.75rem' }}>
            Go back
          </button>
        </div>
      </div>
    );
  }

  if (scenario == null) {
    return (
      <div className="brief" data-testid="setup-page">
        <div className="brief-loading" aria-live="polite" aria-busy="true">
          Loading scenario {scenarioId}…
        </div>
      </div>
    );
  }

  const availableDifficulties = Object.keys(
    scenario.difficulty?.options ?? {},
  ) as ScenarioDifficulty[];

  const validationErrorMap = Object.fromEntries(
    validationResult.errors.map((e) => [e.field, e.message]),
  );

  const formLevelErrors = validationResult.errors.filter((e) => e.field === '_form');

  // The rubric dimensions this scenario scores — the "why am I here" of the
  // brief. Tested is what the debrief will grade; taught is the fallback for a
  // teaching scenario that grades nothing.
  const practisedDimensions =
    scenario.tested_dimensions?.length
      ? scenario.tested_dimensions
      : scenario.taught_dimensions ?? [];

  // The mission. A pack states it as `goals.player_visible` — every official
  // pack does — and it is the one thing issue #500 asks the screen to make
  // unmissable, so it leads the hero.
  //
  // When a scenario declares no goals (a third-party pack, or an engine too old
  // to send the field) the role brief is the only statement of intent the
  // scenario has, so it stands in for them. It is then dropped from the role
  // card below rather than printed twice.
  const objectives = scenario.player_visible_goals ?? [];
  const roleBrief = scenario.player_role?.brief?.trim() ?? '';
  const objectiveStandIn = objectives.length === 0 ? roleBrief : '';
  const hasObjective = objectives.length > 0 || objectiveStandIn !== '';

  // The launch bar's two readouts: what is about to start, and whether it can.
  // The blocker count is deliberately a count, not the messages — each message
  // is already shown in place, next to the control that owns it.
  const launchSummary = [
    difficultyLabel(form.difficulty, scenario.difficulty?.options?.[form.difficulty]),
    languageLabel(form.language),
    INPUT_MODE_SUMMARY[form.input_mode],
    form.tts_enabled ? 'Voice on' : 'Voice off',
  ].join(' · ');

  const blockerCount = validationResult.errors.length;
  // A failed attempt outranks readiness: the setup may still be valid, but the
  // bar must not read "Ready to start" in green directly above the report that
  // starting just failed.
  const launchReady = validationResult.valid && submitError == null;
  const launchStatus = submitError
    ? 'Could not start'
    : validationResult.valid
    ? 'Ready to start'
    : blockerCount === 1
    ? '1 item needs attention'
    : `${blockerCount} items need attention`;

  return (
    <div className="brief" data-testid="setup-page">
      <header className="brief-hero">
        <div className="brief-hero-top">
          <button
            type="button"
            className="brief-back"
            onClick={onBack}
            aria-label="Back to library"
          >
            <span aria-hidden="true">←</span> Back
          </button>
          <span className="brief-eyebrow">Conversation brief</span>
          <span className="brief-eyebrow brief-preflight" aria-hidden="true">Preflight</span>
        </div>

        {/* The mission, in two columns on a wide screen: the situation on the
            left, what success looks like on the right. The objective is the
            brightest thing on the page by design (issue #500) — a player who
            reads nothing else should still come away knowing what they are
            trying to do. */}
        <div className="brief-hero-grid">
          <div className="brief-lede">
            <p className="brief-pack">{scenario.pack_name}</p>
            <h1 className="brief-title">{scenario.title}</h1>
            <p className="brief-summary">{scenario.summary}</p>
          </div>

          {hasObjective && (
            <section
              className="brief-objective"
              aria-labelledby="objective-heading"
              data-testid="brief-objective"
            >
              <div className="brief-objective-head">
                <h2 id="objective-heading" className="brief-objective-title">
                  Your objective
                </h2>
                {objectives.length > 0 && (
                  <span className="brief-objective-count" aria-hidden="true">
                    {objectives.length === 1 ? '1 goal' : `${objectives.length} goals`}
                  </span>
                )}
              </div>
              {objectives.length > 0 ? (
                <ol className="brief-goals">
                  {objectives.map((goal, i) => (
                    <li key={goal} className="brief-goal">
                      {/* The marker is the list's own numbering drawn in the
                          preflight voice, so it is decoration to a screen
                          reader — the <ol> already numbers the items. */}
                      <span className="brief-goal-mark" aria-hidden="true">
                        {String(i + 1).padStart(2, '0')}
                      </span>
                      <span className="brief-goal-text">{goal}</span>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="brief-goal-standin">{objectiveStandIn}</p>
              )}
            </section>
          )}
        </div>

        <ul className="brief-facts" data-testid="brief-facts">
          <li className="brief-fact">
            <span className="brief-fact-label">You play</span>
            <span className="brief-fact-value">{scenario.player_role?.label ?? '—'}</span>
          </li>
          <li className="brief-fact">
            <span className="brief-fact-label">Estimated length</span>
            <span className="brief-fact-value">{scenario.estimated_length_label}</span>
          </li>
          <li className="brief-fact">
            <span className="brief-fact-label">Turn limit</span>
            <span className="brief-fact-value">
              {scenario.duration?.max_turns != null ? `${scenario.duration.max_turns} turns` : '—'}
            </span>
          </li>
          <li className="brief-fact">
            <span className="brief-fact-label">Content rating</span>
            <span className="brief-fact-value">{scenario.content_rating}</span>
          </li>
          <li className="brief-fact">
            <span className="brief-fact-label">Voice</span>
            <span className="brief-fact-value">
              {scenario.voice_supported ? 'Supported' : 'Text only'}
            </span>
          </li>
        </ul>
      </header>

      <form className="brief-body" onSubmit={handleSubmit} noValidate>
        <div className="brief-layout">
          <div className="brief-main">
            {formLevelErrors.length > 0 && (
              <div className="brief-alert" role="alert" data-testid="missing-runtime-block">
                <span className="brief-alert-title">Cannot start yet</span>
                {formLevelErrors.map((e, i) => (
                  <p key={i} className="brief-alert-message">{e.message}</p>
                ))}
                {/* A button into the Model Manager, not prose about Settings: the
                    demo edition hides the model section of Settings, and
                    /model-manager is the one repair path every edition has
                    (issue #495). */}
                <p className="brief-alert-hint">
                  {onInstallModel ? (
                    <button
                      type="button"
                      className="brief-alert-link"
                      onClick={onInstallModel}
                      data-testid="open-model-manager"
                    >
                      Open the Model Manager
                    </button>
                  ) : (
                    <strong>Open the Model Manager</strong>
                  )}{' '}
                  to install a model, then return here to start the conversation.
                </p>
              </div>
            )}

            {/* The two decisions that actually change the conversation carry the
                weight on this tier: how the character behaves, and who the
                player is in the room. */}
            <section className="brief-card is-decision" aria-labelledby="difficulty-heading">
              <div className="brief-card-head">
                <span className="brief-step" aria-hidden="true">01</span>
                <h2 id="difficulty-heading" className="brief-card-title">Difficulty</h2>
                <p className="brief-card-hint">How the character will behave</p>
              </div>
              <div className="brief-options" role="radiogroup" aria-label="Difficulty">
                {availableDifficulties.map((level) => {
                  const option = scenario.difficulty?.options?.[level];
                  const selected = form.difficulty === level;
                  return (
                    <div
                      key={level}
                      className={`brief-option is-level${selected ? ' is-selected' : ''}`}
                      data-level={level}
                      // The meters sit outside the <label> (see TraitMeters), so
                      // the column they occupy would show the row's hover and
                      // selected styling without being clickable. Select on the
                      // whole row so the pointer target matches what the row
                      // looks like; the radio is still the real control, and a
                      // click that reaches it simply sets the same level twice.
                      onClick={() => setField('difficulty', level)}
                    >
                      <label className="brief-option-main">
                        <input
                          type="radio"
                          name="difficulty"
                          value={level}
                          checked={selected}
                          onChange={() => setField('difficulty', level)}
                        />
                        <span className="brief-option-text">
                          <span className="brief-option-name">
                            {difficultyLabel(level, option)}
                            {level === scenario.difficulty?.default && (
                              <span className="brief-option-badge">recommended</span>
                            )}
                          </span>
                          <span className="brief-option-desc">
                            {difficultyDescription(level, option)}
                          </span>
                        </span>
                      </label>
                      <TraitMeters option={option} />
                    </div>
                  );
                })}
              </div>
            </section>

            <section className="brief-card is-decision" aria-labelledby="player-heading">
              <div className="brief-card-head">
                <span className="brief-step" aria-hidden="true">02</span>
                <h2 id="player-heading" className="brief-card-title">Your role</h2>
              </div>
              <div className="brief-card-body">
                {/* Dropped when it is standing in for a missing objective in the
                    hero, rather than printed twice on one screen. */}
                {objectives.length > 0 && roleBrief !== '' && (
                  <p className="brief-role-brief">{roleBrief}</p>
                )}
                <label className="brief-field">
                  <span className="brief-label">Name to use in this session</span>
                  <input
                    type="text"
                    className="brief-input"
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
                    <span id="player-role-error" className="brief-field-error" role="alert">
                      {validationErrorMap['player_role_name']}
                    </span>
                  )}
                </label>
              </div>
            </section>

            {/* ── 03 · Session setup ─────────────────────────────────────────
                The five mechanical settings, grouped into one quiet card. Until
                issue #500 each was a card of its own, identical in weight to the
                difficulty choice above — seven interchangeable blocks, which is
                what made the screen read as a wall of controls. They are demoted
                here, not hidden: there is no disclosure to open, every control is
                still on the screen, and each is still one Tab (or one D-pad
                press) away. */}
            <section className="brief-setup" aria-labelledby="setup-heading">
              <div className="brief-card-head">
                <span className="brief-step" aria-hidden="true">03</span>
                <h2 id="setup-heading" className="brief-card-title">Session setup</h2>
                <p className="brief-card-hint">How you talk, and what is kept</p>
              </div>

              <div className="brief-setup-grid">
                <div className="brief-set">
                  <h3 className="brief-set-title">Input mode</h3>
                  <div className="brief-options" role="radiogroup" aria-label="Input mode">
                    {(
                      [
                        ['text-only', 'Text only', true],
                        ['push-to-talk', 'Push-to-talk voice', runtime.stt_ready],
                        ['hands-free', 'Hands-free voice (VAD)', runtime.stt_ready],
                      ] as [InputMode, string, boolean][]
                    ).map(([value, label, available]) => {
                      const selected = form.input_mode === value;
                      return (
                        <div
                          key={value}
                          className={`brief-option${selected ? ' is-selected' : ''}${
                            !available ? ' is-disabled' : ''
                          }`}
                        >
                          <label className="brief-option-main">
                            <input
                              type="radio"
                              name="input_mode"
                              value={value}
                              checked={selected}
                              disabled={!available}
                              onChange={() => setField('input_mode', value)}
                            />
                            <span className="brief-option-text">
                              <span className="brief-option-name">
                                {label}
                                {!available && value !== 'text-only' && (
                                  <span className="brief-option-note">STT not loaded</span>
                                )}
                              </span>
                            </span>
                          </label>
                        </div>
                      );
                    })}
                  </div>
                  {validationErrorMap['input_mode'] && (
                    <span className="brief-field-error" role="alert">
                      {validationErrorMap['input_mode']}
                    </span>
                  )}
                </div>

                <div className="brief-set">
                  <h3 className="brief-set-title">Audio output</h3>
                  <div className="brief-card-body">
                    <label className="brief-toggle">
                      <input
                        type="checkbox"
                        checked={form.tts_enabled}
                        disabled={!runtime.tts_ready}
                        onChange={(e) => setField('tts_enabled', e.target.checked)}
                        aria-describedby={!runtime.tts_ready ? 'tts-status' : undefined}
                      />
                      <span className="brief-toggle-text">
                        NPC voice (TTS)
                        {runtime.tts_ready && runtime.tts_voice_name && (
                          <span className="brief-badge-ready"> {runtime.tts_voice_name}</span>
                        )}
                        {!runtime.tts_ready && (
                          <span className="brief-badge-off"> — not loaded</span>
                        )}
                      </span>
                    </label>
                    {validationErrorMap['tts_enabled'] && (
                      <span className="brief-field-error" role="alert">
                        {validationErrorMap['tts_enabled']}
                      </span>
                    )}
                    {!runtime.tts_ready && (
                      <p className="brief-note" id="tts-status">
                        Text-only is always available. Install a TTS model to enable voice output.
                      </p>
                    )}
                    {runtime.tts_ready && !scenario.voice_supported && (
                      <p className="brief-note">
                        This scenario is designed for text — TTS can still be enabled but the script
                        was not written with voice in mind.
                      </p>
                    )}
                    {form.tts_enabled && voices.length > 0 && (
                      <label className="brief-field">
                        <span className="brief-label">NPC voice</span>
                        <select
                          className="brief-select"
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
                  </div>
                </div>

                <div className="brief-set">
                  <h3 className="brief-set-title">Language</h3>
                  <label className="brief-field">
                    <span className="brief-label">Conversation language</span>
                    <select
                      className="brief-select"
                      value={form.language}
                      onChange={(e) => setField('language', e.target.value)}
                    >
                      {(scenario.supported_languages ?? ['en']).map((code) => (
                        <option key={code} value={code}>
                          {languageLabel(code)}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                <div className="brief-set">
                  <h3 className="brief-set-title">Privacy</h3>
                  <div className="brief-card-body">
                    <label className="brief-toggle">
                      <input
                        type="checkbox"
                        checked={form.save_transcript}
                        onChange={(e) => setField('save_transcript', e.target.checked)}
                      />
                      <span className="brief-toggle-text">
                        Save transcript locally
                        <span className="brief-toggle-note">
                          {form.save_transcript
                            ? ' — saved to your local data folder only'
                            : ' — not saved'}
                        </span>
                      </span>
                    </label>

                    {scenario.state_meters_permitted && (
                      <label className="brief-toggle">
                        <input
                          type="checkbox"
                          checked={form.show_state_meters}
                          onChange={(e) => setField('show_state_meters', e.target.checked)}
                        />
                        <span className="brief-toggle-text">
                          Show NPC state meters during conversation
                        </span>
                      </label>
                    )}
                    {!scenario.state_meters_permitted && (
                      <p className="brief-note">
                        State meters are hidden in this scenario to preserve realism.
                      </p>
                    )}
                  </div>
                </div>

                <div className="brief-set is-wide">
                  <h3 className="brief-set-title">
                    Variation seed
                    <span className="brief-set-note">Optional</span>
                  </h3>
                  <div className="brief-card-body">
                    <p className="brief-note">
                      The seed controls scenario randomization. Use the same seed to replay an
                      identical variation, or randomize for a new experience.
                    </p>
                    <div className="brief-seed-row">
                      <label className="brief-field brief-seed-field">
                        <span className="brief-label">Seed</span>
                        <input
                          type="number"
                          className="brief-input"
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
                      <button type="button" className="brief-btn-secondary" onClick={handleRandomizeSeed}>
                        Randomize
                      </button>
                      {form.seed !== null && (
                        <button type="button" className="brief-btn-ghost" onClick={handleClearSeed}>
                          Auto
                        </button>
                      )}
                    </div>
                    {validationErrorMap['seed'] && (
                      <span id="seed-error" className="brief-field-error" role="alert">
                        {validationErrorMap['seed']}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </section>

          </div>

          <aside className="brief-aside" aria-label="Scenario information">
            <div className="brief-panel" data-testid="runtime-readiness">
              <h3 className="brief-panel-title">Runtime readiness</h3>
              <ul className="brief-checks">
                <li>
                  <span aria-hidden="true" className={`brief-dot ${runtime.llm_ready ? 'ready' : 'not-ready'}`} />
                  <span>
                    LLM:{' '}
                    {runtime.llm_ready
                      ? runtime.llm_model_name ?? 'ready'
                      : 'not loaded'}
                  </span>
                </li>
                <li>
                  <span aria-hidden="true" className={`brief-dot ${runtime.stt_ready ? 'ready' : 'not-ready'}`} />
                  <span>
                    STT: {runtime.stt_ready ? 'ready' : 'not loaded — voice input unavailable'}
                  </span>
                </li>
                <li>
                  <span aria-hidden="true" className={`brief-dot ${runtime.tts_ready ? 'ready' : 'not-ready'}`} />
                  <span>
                    TTS:{' '}
                    {runtime.tts_ready
                      ? runtime.tts_voice_name ?? 'ready'
                      : 'not loaded — text-only available'}
                  </span>
                </li>
                <li>
                  <span aria-hidden="true" className={`brief-dot ${runtime.stt_ready ? 'ready' : 'not-ready'}`} />
                  <span>
                    VAD: {runtime.stt_ready ? 'available' : 'requires STT'}
                  </span>
                </li>
                <li>
                  <span aria-hidden="true" className={`brief-dot ${runtime.network_required ? 'not-ready' : 'ready'}`} />
                  <span>Network required to play: {runtime.network_required ? 'Yes' : 'No'}</span>
                </li>
              </ul>
            </div>

            {practisedDimensions.length > 0 && (
              <div className="brief-panel" data-testid="brief-practises">
                <h3 className="brief-panel-title">What this practises</h3>
                <ul className="brief-chips">
                  {practisedDimensions.map((dimension) => (
                    <li key={dimension} className="brief-chip">
                      {dimension.replace(/_/g, ' ')}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="brief-panel">
              <h3 className="brief-panel-title">Safety summary</h3>
              <p className="brief-safety">{scenario.safety_summary}</p>
            </div>
          </aside>
        </div>

        {/* The launch bar. Sticky to the bottom of the viewport so the primary
            action is on screen at every scroll position — issue #486 started
            with a player who could not find the start button at all. */}
        <div className="brief-launch" data-testid="brief-launch">
          {/* A failed start belongs to the button that failed. The bar is
              pinned, so the player can press Start from any scroll position —
              an error rendered at the end of the page would be off-screen and
              the press would look like it did nothing at all. */}
          {submitError && (
            <div className="brief-submit-error">
              <ApiErrorView error={submitError} compact context="ScenarioSetup-Submit" />
            </div>
          )}
          <span className="brief-launch-status" role="status">
            <span
              aria-hidden="true"
              className={`brief-dot ${launchReady ? 'ready' : 'not-ready'}`}
            />
            {launchStatus}
          </span>
          <span className="brief-launch-summary" data-testid="brief-launch-summary">
            {launchSummary}
          </span>
          <button
            type="submit"
            className="brief-start"
            disabled={!validationResult.valid || submitting}
            aria-busy={submitting}
          >
            {submitting ? 'Starting…' : 'Start conversation'}
            <span className="brief-start-arrow" aria-hidden="true">→</span>
          </button>
        </div>
      </form>
    </div>
  );
}
