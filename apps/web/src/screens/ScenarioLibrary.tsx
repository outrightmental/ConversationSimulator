// SPDX-License-Identifier: Apache-2.0
import { useState, useEffect, useMemo, useId } from 'react'
import { Link } from 'react-router-dom'
import type { ScenarioInfo, PackValidationResult } from '@convsim/shared'
import { api } from '../api/client'

interface PackGroup {
  pack_id: string
  pack_name: string
  scenarios: ScenarioInfo[]
}

function groupByPack(scenarios: ScenarioInfo[]): PackGroup[] {
  const map = new Map<string, PackGroup>()
  for (const s of scenarios) {
    let g = map.get(s.pack_id)
    if (!g) {
      g = { pack_id: s.pack_id, pack_name: s.pack_name, scenarios: [] }
      map.set(s.pack_id, g)
    }
    g.scenarios.push(s)
  }
  return Array.from(map.values())
}

type ValidationState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'done'; result: PackValidationResult }
  | { status: 'error'; message: string }

export default function ScenarioLibrary() {
  const [scenarios, setScenarios] = useState<ScenarioInfo[] | null>(null)
  const [loadError, setLoadError] = useState(false)
  const [search, setSearch] = useState('')
  const [filterRating, setFilterRating] = useState('')
  const [filterLanguage, setFilterLanguage] = useState('')
  const [filterDifficulty, setFilterDifficulty] = useState('')
  const [filterTag, setFilterTag] = useState('')
  const [filterModel, setFilterModel] = useState('')
  const [voiceOnly, setVoiceOnly] = useState(false)
  const [validations, setValidations] = useState<Record<string, ValidationState>>({})
  const [expandedValidation, setExpandedValidation] = useState<string | null>(null)

  const searchId = useId()
  const ratingId = useId()
  const languageId = useId()
  const difficultyId = useId()
  const tagId = useId()
  const modelId = useId()

  useEffect(() => {
    api
      .listScenarios()
      .then((s) => setScenarios(s))
      .catch(() => setLoadError(true))
  }, [])

  const { allRatings, allLanguages, allDifficulties, allTags, allModels } = useMemo(() => {
    if (!scenarios)
      return { allRatings: [], allLanguages: [], allDifficulties: [], allTags: [], allModels: [] }
    const ratings = new Set<string>()
    const languages = new Set<string>()
    const difficulties = new Set<string>()
    const tags = new Set<string>()
    const models = new Set<string>()
    for (const s of scenarios) {
      ratings.add(s.content_rating)
      for (const l of s.supported_languages) languages.add(l)
      for (const d of Object.keys(s.difficulty.options)) difficulties.add(d)
      for (const t of s.tags ?? []) tags.add(t)
      for (const m of s.recommended_model ?? []) models.add(m)
    }
    return {
      allRatings: [...ratings].sort(),
      allLanguages: [...languages].sort(),
      allDifficulties: [...difficulties].sort(),
      allTags: [...tags].sort(),
      allModels: [...models].sort(),
    }
  }, [scenarios])

  const packs = useMemo(() => {
    if (!scenarios) return []
    const q = search.trim().toLowerCase()
    const filtered = scenarios.filter((s) => {
      if (filterRating && s.content_rating !== filterRating) return false
      if (filterLanguage && !s.supported_languages.includes(filterLanguage)) return false
      if (filterDifficulty && !Object.keys(s.difficulty.options).includes(filterDifficulty)) return false
      if (filterTag && !(s.tags ?? []).includes(filterTag)) return false
      if (filterModel && !(s.recommended_model ?? []).includes(filterModel)) return false
      if (voiceOnly && !s.voice_supported) return false
      if (q) {
        const hay = `${s.title} ${s.summary} ${s.pack_name} ${s.player_role.label}`.toLowerCase()
        if (!hay.includes(q)) return false
      }
      return true
    })
    return groupByPack(filtered)
  }, [scenarios, search, filterRating, filterLanguage, filterDifficulty, filterTag, filterModel, voiceOnly])

  const totalVisible = packs.reduce((n, p) => n + p.scenarios.length, 0)

  async function handleValidate(packId: string) {
    setValidations((prev) => ({ ...prev, [packId]: { status: 'loading' } }))
    setExpandedValidation(packId)
    try {
      const result = await api.validatePack(packId)
      setValidations((prev) => ({ ...prev, [packId]: { status: 'done', result } }))
    } catch (err) {
      setValidations((prev) => ({
        ...prev,
        [packId]: {
          status: 'error',
          message: err instanceof Error ? err.message : 'Validation failed',
        },
      }))
    }
  }

  return (
    <div style={{ maxWidth: '900px' }}>
      <h1>Scenario Library</h1>

      <div
        role="search"
        aria-label="Search and filter scenarios"
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '0.75rem',
          marginBottom: '1.5rem',
          alignItems: 'flex-end',
        }}
      >
        <div
          style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', flex: '1 1 200px', minWidth: '160px' }}
        >
          <label htmlFor={searchId} style={labelStyle}>
            Search
          </label>
          <input
            id={searchId}
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Title, summary, pack…"
            aria-label="Search scenarios"
            style={inputStyle}
          />
        </div>

        <div style={filterGroupStyle}>
          <label htmlFor={ratingId} style={labelStyle}>
            Rating
          </label>
          <select
            id={ratingId}
            value={filterRating}
            onChange={(e) => setFilterRating(e.target.value)}
            style={selectStyle}
            aria-label="Filter by content rating"
          >
            <option value="">All ratings</option>
            {allRatings.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>

        <div style={filterGroupStyle}>
          <label htmlFor={languageId} style={labelStyle}>
            Language
          </label>
          <select
            id={languageId}
            value={filterLanguage}
            onChange={(e) => setFilterLanguage(e.target.value)}
            style={selectStyle}
            aria-label="Filter by language"
          >
            <option value="">All languages</option>
            {allLanguages.map((l) => (
              <option key={l} value={l}>
                {l.toUpperCase()}
              </option>
            ))}
          </select>
        </div>

        <div style={filterGroupStyle}>
          <label htmlFor={difficultyId} style={labelStyle}>
            Difficulty
          </label>
          <select
            id={difficultyId}
            value={filterDifficulty}
            onChange={(e) => setFilterDifficulty(e.target.value)}
            style={selectStyle}
            aria-label="Filter by difficulty"
          >
            <option value="">All difficulties</option>
            {allDifficulties.map((d) => (
              <option key={d} value={d}>
                {d.charAt(0).toUpperCase() + d.slice(1)}
              </option>
            ))}
          </select>
        </div>

        {allTags.length > 0 && (
          <div style={filterGroupStyle}>
            <label htmlFor={tagId} style={labelStyle}>
              Tag
            </label>
            <select
              id={tagId}
              value={filterTag}
              onChange={(e) => setFilterTag(e.target.value)}
              style={selectStyle}
              aria-label="Filter by tag"
            >
              <option value="">All tags</option>
              {allTags.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
        )}

        {allModels.length > 0 && (
          <div style={filterGroupStyle}>
            <label htmlFor={modelId} style={labelStyle}>
              Model
            </label>
            <select
              id={modelId}
              value={filterModel}
              onChange={(e) => setFilterModel(e.target.value)}
              style={selectStyle}
              aria-label="Filter by recommended model"
            >
              <option value="">All models</option>
              {allModels.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>
        )}

        <label
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.4rem',
            fontSize: '0.875rem',
            cursor: 'pointer',
            paddingBottom: '2px',
            color: '#e8e8ea',
          }}
        >
          <input
            type="checkbox"
            checked={voiceOnly}
            onChange={(e) => setVoiceOnly(e.target.checked)}
            aria-label="Show voice-supported scenarios only"
          />
          Voice only
        </label>
      </div>

      {scenarios === null && !loadError && (
        <p aria-live="polite" style={{ color: '#a1a1aa' }}>
          Loading scenarios…
        </p>
      )}

      {loadError && (
        <p role="alert" style={{ color: '#f87171' }}>
          Could not load scenarios. Make sure the local runtime is running.
        </p>
      )}

      {scenarios !== null && scenarios.length === 0 && (
        <div
          data-testid="empty-state"
          role="status"
          style={{
            background: 'rgba(255,255,255,0.03)',
            border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: '8px',
            padding: '2rem',
            textAlign: 'center',
          }}
        >
          <p style={{ fontSize: '1.1rem', marginBottom: '0.5rem' }}>No scenario packs installed.</p>
          <p style={{ fontSize: '0.9rem', color: '#a1a1aa', marginBottom: '1.25rem' }}>
            Import a pack via{' '}
            <Link to="/settings" style={{ color: '#a5b4fc' }}>
              Settings → Import Pack
            </Link>
            , or install an official starter pack to begin.
          </p>
          <Link
            to="/settings"
            style={{
              display: 'inline-block',
              padding: '0.5rem 1.25rem',
              borderRadius: '6px',
              background: 'rgba(255,255,255,0.08)',
              color: '#e8e8ea',
              textDecoration: 'none',
              fontSize: '0.875rem',
            }}
          >
            Go to Settings
          </Link>
        </div>
      )}

      {scenarios !== null && scenarios.length > 0 && (
        <>
          <p
            aria-live="polite"
            aria-atomic="true"
            data-testid="results-count"
            style={{ fontSize: '0.875rem', color: '#71717a', marginBottom: '1.25rem' }}
          >
            {totalVisible === 0
              ? 'No scenarios match the current filters.'
              : `${totalVisible} scenario${totalVisible === 1 ? '' : 's'} in ${packs.length} pack${packs.length === 1 ? '' : 's'}`}
          </p>

          {totalVisible === 0 && (
            <p data-testid="no-results" style={{ color: '#a1a1aa', fontSize: '0.9rem' }}>
              Try adjusting your search or clearing a filter.
            </p>
          )}
        </>
      )}

      {packs.map((pack) => {
        const validation: ValidationState = validations[pack.pack_id] ?? { status: 'idle' }
        const isExpanded = expandedValidation === pack.pack_id

        return (
          <section
            key={pack.pack_id}
            aria-labelledby={`pack-heading-${pack.pack_id}`}
            style={{ marginBottom: '2.5rem' }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'baseline',
                justifyContent: 'space-between',
                gap: '1rem',
                marginBottom: '0.5rem',
                borderBottom: '1px solid rgba(255,255,255,0.08)',
                paddingBottom: '0.5rem',
              }}
            >
              <h2
                id={`pack-heading-${pack.pack_id}`}
                style={{ fontSize: '1rem', fontWeight: 600, margin: 0 }}
              >
                {pack.pack_name}
                <span
                  style={{ fontWeight: 400, color: '#71717a', marginLeft: '0.5rem', fontSize: '0.875rem' }}
                >
                  ({pack.scenarios.length}{' '}
                  {pack.scenarios.length === 1 ? 'scenario' : 'scenarios'})
                </span>
              </h2>

              <button
                onClick={() => {
                  if (isExpanded && validation.status !== 'idle') {
                    setExpandedValidation(null)
                  } else {
                    void handleValidate(pack.pack_id)
                  }
                }}
                disabled={validation.status === 'loading'}
                aria-label={`Validate pack ${pack.pack_name}`}
                aria-expanded={isExpanded && validation.status !== 'idle'}
                data-testid={`validate-${pack.pack_id}`}
                style={{
                  padding: '0.25rem 0.65rem',
                  borderRadius: '4px',
                  border: '1px solid rgba(255,255,255,0.15)',
                  cursor: validation.status === 'loading' ? 'wait' : 'pointer',
                  background: 'transparent',
                  color: '#a1a1aa',
                  fontSize: '0.8rem',
                  flexShrink: 0,
                }}
              >
                {validation.status === 'loading' ? 'Validating…' : 'Validate pack'}
              </button>
            </div>

            {isExpanded && validation.status === 'done' && (
              <div
                data-testid={`validation-result-${pack.pack_id}`}
                role="status"
                style={{
                  marginBottom: '0.75rem',
                  padding: '0.6rem 0.85rem',
                  borderRadius: '4px',
                  fontSize: '0.85rem',
                  background: validation.result.valid
                    ? 'rgba(34,197,94,0.08)'
                    : 'rgba(239,68,68,0.08)',
                  border: `1px solid ${
                    validation.result.valid ? 'rgba(34,197,94,0.25)' : 'rgba(239,68,68,0.25)'
                  }`,
                  color: validation.result.valid ? '#86efac' : '#fca5a5',
                }}
              >
                {validation.result.valid ? (
                  <span>Pack is valid — no issues found.</span>
                ) : (
                  <>
                    <p style={{ margin: '0 0 0.4rem', fontWeight: 500 }}>
                      {validation.result.errors.length} validation error
                      {validation.result.errors.length === 1 ? '' : 's'} found:
                    </p>
                    <ul role="list" style={{ margin: 0, paddingLeft: '1.25rem' }}>
                      {validation.result.errors.map((e, i) => (
                        <li key={i} data-testid="validation-error">
                          {e.rule_id && (
                            <code
                              style={{ fontSize: '0.78rem', marginRight: '0.35rem', color: '#fbbf24' }}
                            >
                              [{e.rule_id}]
                            </code>
                          )}
                          {e.file_path && (
                            <code
                              style={{ fontSize: '0.78rem', marginRight: '0.35rem', color: '#94a3b8' }}
                            >
                              {e.file_path}:
                            </code>
                          )}
                          {e.message}
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </div>
            )}

            {isExpanded && validation.status === 'error' && (
              <p
                role="alert"
                style={{ fontSize: '0.85rem', color: '#f87171', marginBottom: '0.75rem' }}
              >
                {validation.message}
              </p>
            )}

            <ul
              role="list"
              aria-label={`Scenarios in ${pack.pack_name}`}
              style={{
                listStyle: 'none',
                padding: 0,
                margin: 0,
                display: 'flex',
                flexDirection: 'column',
                gap: '0.75rem',
              }}
            >
              {pack.scenarios.map((scenario) => (
                <li key={scenario.scenario_id}>
                  <article
                    aria-labelledby={`scenario-title-${scenario.scenario_id}`}
                    style={{
                      border: '1px solid rgba(255,255,255,0.1)',
                      borderRadius: '8px',
                      padding: '1rem 1.25rem',
                      background: 'rgba(255,255,255,0.02)',
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'flex-start',
                        gap: '1rem',
                      }}
                    >
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <h3
                          id={`scenario-title-${scenario.scenario_id}`}
                          style={{ fontSize: '0.95rem', fontWeight: 600, margin: '0 0 0.3rem' }}
                        >
                          {scenario.title}
                        </h3>
                        <p
                          style={{
                            fontSize: '0.875rem',
                            color: '#a1a1aa',
                            margin: '0 0 0.75rem',
                            lineHeight: '1.5',
                          }}
                        >
                          {scenario.summary}
                        </p>

                        <div
                          style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem' }}
                          aria-label="Scenario details"
                        >
                          <Chip label={scenario.content_rating} />
                          <Chip label={`Role: ${scenario.player_role.label}`} />
                          <Chip label={scenario.estimated_length_label} />
                          {scenario.voice_supported && (
                            <Chip label="Voice supported" accent="green" />
                          )}
                          {scenario.supported_languages.map((l) => (
                            <Chip key={l} label={l.toUpperCase()} />
                          ))}
                          {Object.keys(scenario.difficulty.options).map((d) => (
                            <Chip key={d} label={d.charAt(0).toUpperCase() + d.slice(1)} />
                          ))}
                          {(scenario.tags ?? []).map((t) => (
                            <Chip key={t} label={t} accent="blue" />
                          ))}
                          {(scenario.recommended_model ?? []).map((m) => (
                            <Chip key={m} label={m} accent="model" />
                          ))}
                        </div>
                      </div>

                      <Link
                        to={`/setup/${scenario.scenario_id}`}
                        aria-label={`Launch ${scenario.title}`}
                        data-testid={`launch-${scenario.scenario_id}`}
                        style={{
                          flexShrink: 0,
                          padding: '0.4rem 1rem',
                          borderRadius: '6px',
                          background: 'rgba(99,102,241,0.15)',
                          border: '1px solid rgba(99,102,241,0.4)',
                          color: '#a5b4fc',
                          textDecoration: 'none',
                          fontSize: '0.875rem',
                          fontWeight: 500,
                          whiteSpace: 'nowrap',
                        }}
                      >
                        Launch
                      </Link>
                    </div>
                  </article>
                </li>
              ))}
            </ul>
          </section>
        )
      })}
    </div>
  )
}

function Chip({ label, accent }: { label: string; accent?: 'green' | 'blue' | 'model' }) {
  const green = accent === 'green'
  const blue = accent === 'blue'
  const model = accent === 'model'
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '0.1rem 0.45rem',
        borderRadius: '4px',
        fontSize: '0.75rem',
        background: green
          ? 'rgba(34,197,94,0.12)'
          : blue
            ? 'rgba(99,102,241,0.12)'
            : model
              ? 'rgba(234,179,8,0.1)'
              : 'rgba(255,255,255,0.06)',
        color: green ? '#86efac' : blue ? '#a5b4fc' : model ? '#fde68a' : '#a1a1aa',
        border: green
          ? '1px solid rgba(34,197,94,0.2)'
          : blue
            ? '1px solid rgba(99,102,241,0.2)'
            : model
              ? '1px solid rgba(234,179,8,0.2)'
              : '1px solid rgba(255,255,255,0.08)',
      }}
    >
      {label}
    </span>
  )
}

const inputStyle: React.CSSProperties = {
  padding: '0.4rem 0.6rem',
  borderRadius: '4px',
  border: '1px solid rgba(255,255,255,0.15)',
  background: 'rgba(255,255,255,0.05)',
  color: '#e8e8ea',
  fontSize: '0.875rem',
  width: '100%',
  boxSizing: 'border-box',
}

const selectStyle: React.CSSProperties = {
  padding: '0.4rem 0.6rem',
  borderRadius: '4px',
  border: '1px solid rgba(255,255,255,0.15)',
  background: 'rgba(255,255,255,0.05)',
  color: '#e8e8ea',
  fontSize: '0.875rem',
  cursor: 'pointer',
  width: '100%',
}

const filterGroupStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: '0.25rem',
  flex: '0 1 150px',
  minWidth: '120px',
}

const labelStyle: React.CSSProperties = {
  fontSize: '0.8rem',
  color: '#a1a1aa',
}
