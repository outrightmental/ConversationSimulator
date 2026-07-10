// SPDX-License-Identifier: Apache-2.0
import { useState, useEffect, useMemo, useId, useRef } from 'react'
import { Link } from 'react-router-dom'
import type { ScenarioInfo, PackValidationResult } from '@convsim/shared'
import { api } from '../api/client'
import type { PackSummary, ImportPackResponse } from '../api/client'
import type { ApiError } from '../api/errors'
import { ApiErrorView } from '../components/ApiErrorView'

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

type ImportState = 'idle' | 'uploading' | 'success' | 'error'

export default function ScenarioLibrary() {
  const [scenarios, setScenarios] = useState<ScenarioInfo[] | null>(null)
  const [loadError, setLoadError] = useState<ApiError | null>(null)
  const [search, setSearch] = useState('')
  const [filterRating, setFilterRating] = useState('')
  const [filterLanguage, setFilterLanguage] = useState('')
  const [filterDifficulty, setFilterDifficulty] = useState('')
  const [filterTag, setFilterTag] = useState('')
  const [filterModel, setFilterModel] = useState('')
  const [voiceOnly, setVoiceOnly] = useState(false)
  const [validations, setValidations] = useState<Record<string, ValidationState>>({})
  const [expandedValidation, setExpandedValidation] = useState<string | null>(null)

  // Indexed packs (from PackIndex) for folder display
  const [indexedPacks, setIndexedPacks] = useState<Record<string, PackSummary>>({})
  const [folderOpen, setFolderOpen] = useState<string | null>(null)

  // Import pack state
  const [importState, setImportState] = useState<ImportState>('idle')
  const [importError, setImportError] = useState<string | null>(null)
  const [importedPack, setImportedPack] = useState<ImportPackResponse | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Model readiness warning
  const [modelMissing, setModelMissing] = useState(false)

  const searchId = useId()
  const ratingId = useId()
  const languageId = useId()
  const difficultyId = useId()
  const tagId = useId()
  const modelId = useId()

  function loadScenarios() {
    void api.listScenarios().then((r) => {
      if (r.ok) { setScenarios(r.data); setLoadError(null) }
      else setLoadError(r.error)
    })
  }

  function loadIndexedPacks() {
    void api.listPacks().then((r) => {
      if (r.ok) {
        const map: Record<string, PackSummary> = {}
        for (const p of r.data.packs) map[p.pack_id] = p
        setIndexedPacks(map)
      }
    })
  }

  useEffect(() => {
    loadScenarios()
    loadIndexedPacks()

    void api.getModels().then((r) => {
      if (r.ok) {
        const { status } = r.data.runtime_health
        setModelMissing(status !== 'ready' && status !== 'degraded')
      }
    })
  }, [])

  const { allRatings, allLanguages, allDifficulties, allTags, allModels } = useMemo(() => {
    if (!scenarios) return { allRatings: [], allLanguages: [], allDifficulties: [], allTags: [], allModels: [] }
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
    const r = await api.validatePack(packId)
    if (r.ok) {
      setValidations((prev) => ({ ...prev, [packId]: { status: 'done', result: r.data } }))
    } else {
      setValidations((prev) => ({ ...prev, [packId]: { status: 'error', message: r.error.message } }))
    }
  }

  async function handleImportPack(file: File) {
    setImportState('uploading')
    setImportError(null)
    setImportedPack(null)
    const r = await api.importPack(file)
    if (r.ok) {
      setImportedPack(r.data)
      setImportState('success')
      loadScenarios()
      loadIndexedPacks()
    } else {
      setImportError(r.error.message)
      setImportState('error')
    }
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) void handleImportPack(file)
    e.target.value = ''
  }

  return (
    <div style={{ maxWidth: '900px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h1 style={{ margin: 0 }}>Scenario Library</h1>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          {importState === 'success' && importedPack && (
            <span
              data-testid="import-success"
              style={{ fontSize: '0.85rem', color: '#86efac' }}
            >
              Imported "{importedPack.name}" ({importedPack.pack_id})
            </span>
          )}
          {importState === 'error' && importError && (
            <span
              role="alert"
              data-testid="import-error"
              style={{ fontSize: '0.85rem', color: '#f87171' }}
            >
              {importError}
            </span>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept=".zip,application/zip"
            style={{ display: 'none' }}
            aria-label="Select pack zip file"
            data-testid="import-file-input"
            onChange={handleFileChange}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={importState === 'uploading'}
            data-testid="import-pack-button"
            aria-label="Import pack"
            style={{
              padding: '0.4rem 0.85rem',
              borderRadius: '6px',
              border: '1px solid rgba(255,255,255,0.15)',
              background: 'rgba(255,255,255,0.05)',
              color: '#e8e8ea',
              fontSize: '0.875rem',
              cursor: importState === 'uploading' ? 'wait' : 'pointer',
            }}
          >
            {importState === 'uploading' ? 'Importing…' : 'Import pack'}
          </button>
        </div>
      </div>

      {modelMissing && (
        <div
          role="alert"
          data-testid="model-missing-banner"
          style={{
            background: 'rgba(251,191,36,0.08)',
            border: '1px solid rgba(251,191,36,0.3)',
            borderRadius: '6px',
            padding: '0.75rem 1rem',
            marginBottom: '1.25rem',
            fontSize: '0.875rem',
            color: '#fbbf24',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: '1rem',
          }}
        >
          <span>No model is ready. Launching a scenario requires a local or API-connected model.</span>
          <Link
            to="/model-manager"
            data-testid="model-manager-link"
            style={{
              flexShrink: 0,
              padding: '0.3rem 0.75rem',
              borderRadius: '4px',
              border: '1px solid rgba(251,191,36,0.4)',
              color: '#fbbf24',
              textDecoration: 'none',
              fontSize: '0.8rem',
              whiteSpace: 'nowrap',
            }}
          >
            Set up model
          </Link>
        </div>
      )}

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
        <ApiErrorView
          error={loadError}
          onRetry={() => { loadScenarios(); loadIndexedPacks() }}
          context="ScenarioLibrary"
        />
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
          <p style={{ fontSize: '0.9rem', color: '#a1a1aa', marginBottom: '0.5rem' }}>
            Packs are collections of practice conversations. Import a pack zip file using the
            button above, or install an official starter pack to begin.
          </p>
          <p style={{ fontSize: '0.875rem', color: '#71717a', marginBottom: '1.25rem' }}>
            You can also{' '}
            <a
              href="https://github.com/outrightmental/ConversationSimulator/wiki"
              target="_blank"
              rel="noreferrer"
              style={{ color: '#71717a' }}
            >
              browse the docs
            </a>{' '}
            for a link to official packs or the pack authoring guide.
          </p>
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={importState === 'uploading'}
            data-testid="empty-import-pack-button"
            style={{
              display: 'inline-block',
              padding: '0.5rem 1.25rem',
              borderRadius: '6px',
              background: 'rgba(255,255,255,0.08)',
              color: '#e8e8ea',
              border: '1px solid rgba(255,255,255,0.15)',
              cursor: importState === 'uploading' ? 'wait' : 'pointer',
              fontSize: '0.875rem',
            }}
          >
            {importState === 'uploading' ? 'Importing…' : 'Import pack'}
          </button>
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
        const indexedPack = indexedPacks[pack.pack_id]
        const isFolderOpen = folderOpen === pack.pack_id

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

              <div style={{ display: 'flex', gap: '0.5rem', flexShrink: 0 }}>
                {indexedPack && (
                  <button
                    onClick={() => setFolderOpen(isFolderOpen ? null : pack.pack_id)}
                    aria-label={`Open folder for pack ${pack.pack_name}`}
                    aria-expanded={isFolderOpen}
                    data-testid={`open-folder-${pack.pack_id}`}
                    style={packActionButtonStyle}
                  >
                    {isFolderOpen ? 'Hide folder' : 'Open folder'}
                  </button>
                )}
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
                    ...packActionButtonStyle,
                    cursor: validation.status === 'loading' ? 'wait' : 'pointer',
                  }}
                >
                  {validation.status === 'loading' ? 'Validating…' : 'Validate pack'}
                </button>
              </div>
            </div>

            {isFolderOpen && indexedPack?.pack_root && (
              <div
                data-testid={`folder-path-${pack.pack_id}`}
                style={{
                  marginBottom: '0.75rem',
                  padding: '0.6rem 0.85rem',
                  borderRadius: '4px',
                  background: 'rgba(255,255,255,0.04)',
                  border: '1px solid rgba(255,255,255,0.1)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.75rem',
                }}
              >
                <code style={{ fontSize: '0.78rem', color: '#94a3b8', flex: 1, wordBreak: 'break-all' }}>
                  {indexedPack.pack_root}
                </code>
                <button
                  onClick={() => void navigator.clipboard.writeText(indexedPack.pack_root ?? '')}
                  aria-label="Copy pack folder path"
                  data-testid={`copy-folder-${pack.pack_id}`}
                  style={{
                    ...packActionButtonStyle,
                    flexShrink: 0,
                  }}
                >
                  Copy
                </button>
              </div>
            )}

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
                    <p style={{ margin: '0.6rem 0 0', fontSize: '0.8rem', color: '#a1a1aa' }}>
                      Fix the errors above in the pack source files, then re-import the pack.{' '}
                      <a
                        href="https://github.com/outrightmental/ConversationSimulator/wiki"
                        target="_blank"
                        rel="noreferrer"
                        style={{ color: '#94a3b8' }}
                        aria-label="Pack authoring guide"
                      >
                        Pack authoring guide
                      </a>
                    </p>
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
                            <Chip key={m} label={m} accent="purple" />
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

function Chip({ label, accent }: { label: string; accent?: 'green' | 'blue' | 'purple' }) {
  const green = accent === 'green'
  const blue = accent === 'blue'
  const purple = accent === 'purple'
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
            : purple
              ? 'rgba(168,85,247,0.12)'
              : 'rgba(255,255,255,0.06)',
        color: green ? '#86efac' : blue ? '#a5b4fc' : purple ? '#d8b4fe' : '#a1a1aa',
        border: green
          ? '1px solid rgba(34,197,94,0.2)'
          : blue
            ? '1px solid rgba(99,102,241,0.2)'
            : purple
              ? '1px solid rgba(168,85,247,0.2)'
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

const packActionButtonStyle: React.CSSProperties = {
  padding: '0.25rem 0.65rem',
  borderRadius: '4px',
  border: '1px solid rgba(255,255,255,0.15)',
  cursor: 'pointer',
  background: 'transparent',
  color: '#a1a1aa',
  fontSize: '0.8rem',
}
