// SPDX-License-Identifier: Apache-2.0
import { useState, useEffect, useCallback } from 'react'
import { api } from '../api/client'
import type { ModelsResponse, RuntimeSettings } from '@convsim/shared'
import type { ApiError } from '../api/errors'
import { ApiErrorView } from './ApiErrorView'

const DOCS_URL = 'https://docs.conversationsimulator.com/play/local-models/'

const PROVIDER_NAMES: Record<string, string> = {
  llama_cpp: 'llama.cpp',
  ollama: 'Ollama',
  fake: 'Fake (Demo)',
}

const STATUS_COLORS: Record<string, string> = {
  ready: '#86efac',
  starting: '#fbbf24',
  degraded: '#fb923c',
  error: '#f87171',
  unavailable: '#71717a',
}

interface FieldError {
  field: string
  message: string
}

function parseFloat2(s: string): number | null {
  if (s === '' || s === null || s === undefined) return null
  const n = parseFloat(s)
  return isNaN(n) ? null : n
}

function parseInt2(s: string): number | null {
  if (s === '' || s === null || s === undefined) return null
  const n = parseInt(s, 10)
  return isNaN(n) ? null : n
}

function settingsToForm(s: RuntimeSettings): Record<keyof RuntimeSettings, string> {
  return {
    context_length: s.context_length !== null ? String(s.context_length) : '',
    gpu_layers: s.gpu_layers !== null ? String(s.gpu_layers) : '',
    threads: s.threads !== null ? String(s.threads) : '',
    temperature: s.temperature !== null ? String(s.temperature) : '',
    top_p: s.top_p !== null ? String(s.top_p) : '',
    repeat_penalty: s.repeat_penalty !== null ? String(s.repeat_penalty) : '',
  }
}

function validateForm(form: Record<keyof RuntimeSettings, string>): FieldError[] {
  const errs: FieldError[] = []

  const cl = parseInt2(form.context_length)
  if (form.context_length !== '' && (cl === null || !Number.isInteger(cl) || cl < 512 || cl > 131072)) {
    errs.push({ field: 'context_length', message: 'Must be an integer between 512 and 131072.' })
  }

  const gl = parseInt2(form.gpu_layers)
  if (form.gpu_layers !== '' && (gl === null || !Number.isInteger(gl) || gl < -1 || gl > 256)) {
    errs.push({ field: 'gpu_layers', message: 'Must be an integer between -1 (all layers to GPU) and 256.' })
  }

  const th = parseInt2(form.threads)
  if (form.threads !== '' && (th === null || !Number.isInteger(th) || th < 1 || th > 64)) {
    errs.push({ field: 'threads', message: 'Must be an integer between 1 and 64.' })
  }

  const temp = parseFloat2(form.temperature)
  if (form.temperature !== '' && (temp === null || temp < 0.0 || temp > 2.0)) {
    errs.push({ field: 'temperature', message: 'Must be between 0.0 and 2.0.' })
  }

  const tp = parseFloat2(form.top_p)
  if (form.top_p !== '' && (tp === null || tp < 0.0 || tp > 1.0)) {
    errs.push({ field: 'top_p', message: 'Must be between 0.0 and 1.0.' })
  }

  const rp = parseFloat2(form.repeat_penalty)
  if (form.repeat_penalty !== '' && (rp === null || rp < 1.0 || rp > 2.0)) {
    errs.push({ field: 'repeat_penalty', message: 'Must be between 1.0 and 2.0.' })
  }

  return errs
}

function formToRequest(form: Record<keyof RuntimeSettings, string>): Partial<RuntimeSettings> {
  return {
    context_length: parseInt2(form.context_length),
    gpu_layers: parseInt2(form.gpu_layers),
    threads: parseInt2(form.threads),
    temperature: parseFloat2(form.temperature),
    top_p: parseFloat2(form.top_p),
    repeat_penalty: parseFloat2(form.repeat_penalty),
  }
}

const inputStyle: React.CSSProperties = {
  padding: '0.3rem 0.5rem',
  borderRadius: '4px',
  border: '1px solid rgba(255,255,255,0.15)',
  background: 'rgba(255,255,255,0.05)',
  color: 'inherit',
  fontSize: '0.875rem',
  width: '120px',
}

const selectStyle: React.CSSProperties = {
  padding: '0.3rem 0.5rem',
  borderRadius: '4px',
  border: '1px solid rgba(255,255,255,0.15)',
  background: '#1a1a1a',
  color: 'inherit',
  fontSize: '0.875rem',
  minWidth: '160px',
}

const rowStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'flex-start',
  gap: '0.75rem',
  marginBottom: '0.75rem',
  flexWrap: 'wrap',
}

const labelStyle: React.CSSProperties = {
  fontSize: '0.875rem',
  color: '#a1a1aa',
  minWidth: '140px',
  paddingTop: '0.35rem',
}

const noteStyle: React.CSSProperties = {
  fontSize: '0.75rem',
  color: '#71717a',
  marginTop: '0.2rem',
}

const errorStyle: React.CSSProperties = {
  fontSize: '0.75rem',
  color: '#f87171',
  marginTop: '0.2rem',
}

const btnStyle: React.CSSProperties = {
  padding: '0.35rem 0.9rem',
  borderRadius: '4px',
  border: '1px solid rgba(255,255,255,0.15)',
  background: 'rgba(255,255,255,0.06)',
  color: 'inherit',
  cursor: 'pointer',
  fontSize: '0.875rem',
  fontWeight: 500,
}

const primaryBtnStyle: React.CSSProperties = {
  ...btnStyle,
  background: 'rgba(99,102,241,0.2)',
  border: '1px solid rgba(99,102,241,0.4)',
  color: '#a5b4fc',
}

function FieldRow({
  label,
  children,
  error,
  note,
}: {
  label: string
  children: React.ReactNode
  error?: string
  note?: string
}) {
  return (
    <div style={rowStyle}>
      <span style={labelStyle}>{label}</span>
      <div>
        {children}
        {note && <div style={noteStyle}>{note}</div>}
        {error && <div style={errorStyle} role="alert">{error}</div>}
      </div>
    </div>
  )
}

export default function RuntimeSettingsPanel() {
  const [modelsData, setModelsData] = useState<ModelsResponse | null>(null)
  const [loadError, setLoadError] = useState<ApiError | null>(null)

  const [provider, setProvider] = useState<string>('llama_cpp')
  const [modelId, setModelId] = useState<string>('')

  const [basicApplying, setBasicApplying] = useState(false)
  const [basicApplyError, setBasicApplyError] = useState<ApiError | null>(null)
  const [basicApplySuccess, setBasicApplySuccess] = useState(false)

  const [showAdvanced, setShowAdvanced] = useState(false)
  const [form, setForm] = useState<Record<keyof RuntimeSettings, string>>({
    context_length: '',
    gpu_layers: '',
    threads: '',
    temperature: '',
    top_p: '',
    repeat_penalty: '',
  })
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [advApplying, setAdvApplying] = useState(false)
  const [advApplyError, setAdvApplyError] = useState<ApiError | null>(null)
  const [requiresRestart, setRequiresRestart] = useState(false)
  const [resetting, setResetting] = useState(false)
  const [resetError, setResetError] = useState<ApiError | null>(null)

  const loadData = useCallback(async () => {
    setLoadError(null)
    const [modelsR, settingsR] = await Promise.all([api.getModels(), api.getRuntimeSettings()])
    if (!modelsR.ok) { setLoadError(modelsR.error); return }
    if (!settingsR.ok) { setLoadError(settingsR.error); return }
    setModelsData(modelsR.data)
    setProvider(modelsR.data.active.runtime_id ?? 'llama_cpp')
    setModelId(modelsR.data.active.model_id ?? '')
    setForm(settingsToForm(settingsR.data.settings))
    setRequiresRestart(false)
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const modelOptions = (() => {
    if (!modelsData) return []
    if (provider === 'ollama') {
      return modelsData.ollama_models.map((m) => ({ value: m.id, label: m.name }))
    }
    if (provider === 'llama_cpp') {
      return modelsData.installed
        .filter((m) => m.install_status === 'ready')
        .map((m) => ({ value: m.file_path, label: m.filename }))
    }
    return []
  })()

  async function handleBasicApply() {
    setBasicApplying(true)
    setBasicApplyError(null)
    setBasicApplySuccess(false)
    const r = await api.useModel({ runtime_id: provider, model_id: modelId || null })
    if (!r.ok) { setBasicApplyError(r.error); setBasicApplying(false); return }
    setBasicApplySuccess(true)
    setBasicApplying(false)
    loadData()
  }

  function handleFieldChange(field: keyof RuntimeSettings, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }))
    setFieldErrors((prev) => {
      const next = { ...prev }
      delete next[field]
      return next
    })
    setRequiresRestart(false)
    setAdvApplyError(null)
  }

  async function handleAdvancedApply() {
    const errs = validateForm(form)
    if (errs.length > 0) {
      const map: Record<string, string> = {}
      for (const e of errs) map[e.field] = e.message
      setFieldErrors(map)
      return
    }
    setAdvApplying(true)
    setAdvApplyError(null)
    const r = await api.updateRuntimeSettings(formToRequest(form))
    if (!r.ok) { setAdvApplyError(r.error); setAdvApplying(false); return }
    setRequiresRestart(r.data.requires_restart)
    setForm(settingsToForm(r.data.settings))
    setAdvApplying(false)
  }

  async function handleReset() {
    setResetting(true)
    setResetError(null)
    const r = await api.resetRuntimeSettings()
    if (!r.ok) { setResetError(r.error); setResetting(false); return }
    setForm(settingsToForm(r.data.settings))
    setFieldErrors({})
    setRequiresRestart(r.data.requires_restart)
    setAdvApplyError(null)
    setResetting(false)
  }

  const health = modelsData?.runtime_health
  const lastBenchmark = modelsData?.last_benchmark

  if (loadError) {
    return <ApiErrorView error={loadError} onRetry={loadData} context="RuntimeSettingsPanel" />
  }

  if (!modelsData) {
    return <p style={{ fontSize: '0.875rem', color: '#a1a1aa' }}>Loading…</p>
  }

  return (
    <div>
      {/* Basic settings: provider + model */}
      <div style={{ marginBottom: '1rem' }}>
        <div style={rowStyle}>
          <span style={labelStyle}>Provider</span>
          <select
            aria-label="provider"
            value={provider}
            onChange={(e) => { setProvider(e.target.value); setModelId('') }}
            style={selectStyle}
          >
            <option value="llama_cpp">llama.cpp</option>
            <option value="ollama">Ollama</option>
            <option value="fake">Fake (Demo)</option>
          </select>
        </div>

        {provider !== 'fake' && (
          <div style={rowStyle}>
            <span style={labelStyle}>Model</span>
            <div>
              <select
                aria-label="model"
                value={modelId}
                onChange={(e) => setModelId(e.target.value)}
                style={selectStyle}
              >
                <option value="">— none selected —</option>
                {modelOptions.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
              {modelOptions.length === 0 && (
                <div style={noteStyle}>
                  No {PROVIDER_NAMES[provider]} models found.{' '}
                  {provider === 'llama_cpp' && (
                    <a
                      href="/models"
                      style={{ color: '#818cf8' }}
                    >
                      Install a model
                    </a>
                  )}
                  {provider === 'ollama' && (
                    <>
                      Ensure Ollama is running.{' '}
                      <a
                        href={DOCS_URL}
                        target="_blank"
                        rel="noreferrer"
                        style={{ color: '#818cf8' }}
                        aria-label="troubleshooting docs"
                      >
                        Troubleshooting docs
                      </a>
                    </>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {basicApplyError && <ApiErrorView error={basicApplyError} compact context="RuntimeSettingsPanel-BasicApply" />}
        {basicApplySuccess && (
          <p aria-live="polite" style={{ fontSize: '0.875rem', color: '#86efac', marginBottom: '0.5rem' }}>
            Provider and model updated.
          </p>
        )}

        <button
          aria-label="apply provider and model"
          onClick={handleBasicApply}
          disabled={basicApplying}
          style={{ ...primaryBtnStyle, cursor: basicApplying ? 'wait' : 'pointer' }}
        >
          {basicApplying ? 'Applying…' : 'Apply'}
        </button>
      </div>

      {/* Health status */}
      {health && (
        <div
          aria-label="runtime health"
          style={{
            padding: '0.6rem 0.75rem',
            borderRadius: '6px',
            background: 'rgba(255,255,255,0.04)',
            border: '1px solid rgba(255,255,255,0.08)',
            fontSize: '0.85rem',
            marginBottom: '1rem',
          }}
        >
          <span
            style={{
              display: 'inline-block',
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              background: STATUS_COLORS[health.status] ?? '#71717a',
              marginRight: '0.5rem',
              verticalAlign: 'middle',
            }}
          />
          <span style={{ color: STATUS_COLORS[health.status] ?? '#71717a', fontWeight: 500 }}>
            {health.runtime_name}
          </span>
          {health.model_id && (
            <span style={{ color: '#a1a1aa', marginLeft: '0.5rem' }}>
              — {health.model_id}
            </span>
          )}
          {health.message && (
            <span style={{ color: '#71717a', marginLeft: '0.5rem', fontSize: '0.8rem' }}>
              {health.message}
            </span>
          )}
        </div>
      )}

      {/* Last benchmark */}
      {lastBenchmark && (
        <div
          aria-label="last benchmark result"
          style={{
            padding: '0.5rem 0.75rem',
            borderRadius: '6px',
            background: 'rgba(255,255,255,0.03)',
            border: '1px solid rgba(255,255,255,0.07)',
            fontSize: '0.82rem',
            color: '#a1a1aa',
            marginBottom: '1rem',
          }}
        >
          Last benchmark:{' '}
          <span style={{ color: '#d4d4d8', fontWeight: 500 }}>
            {lastBenchmark.tokens_per_sec.toFixed(1)} tokens/sec
          </span>
          {lastBenchmark.context_length != null && (
            <span style={{ marginLeft: '0.5rem' }}>
              · {lastBenchmark.context_length.toLocaleString()} token context
            </span>
          )}
          {lastBenchmark.warnings.length > 0 && (
            <span style={{ marginLeft: '0.5rem', color: '#fbbf24' }}>
              · {lastBenchmark.warnings.length} warning{lastBenchmark.warnings.length > 1 ? 's' : ''}
            </span>
          )}
        </div>
      )}

      {/* Advanced toggle */}
      <button
        onClick={() => setShowAdvanced((v) => !v)}
        aria-expanded={showAdvanced}
        aria-label={showAdvanced ? 'hide runtime advanced settings' : 'show runtime advanced settings'}
        style={{
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          color: '#71717a',
          fontSize: '0.85rem',
          padding: 0,
          marginBottom: '0.75rem',
        }}
      >
        {showAdvanced ? '▾ Hide runtime advanced settings' : '▸ Show runtime advanced settings'}
      </button>

      {showAdvanced && (
        <div
          style={{
            borderLeft: '2px solid rgba(255,255,255,0.08)',
            paddingLeft: '1rem',
            marginBottom: '1rem',
          }}
        >
          <FieldRow
            label="Context length"
            error={fieldErrors['context_length']}
            note="Tokens the model can process at once. Leave blank to use the model default. Changing this requires a runtime restart."
          >
            <input
              aria-label="context length"
              type="number"
              min={512}
              max={131072}
              step={512}
              placeholder="model default"
              value={form.context_length}
              onChange={(e) => handleFieldChange('context_length', e.target.value)}
              style={inputStyle}
            />
          </FieldRow>

          <FieldRow
            label="GPU layers"
            error={fieldErrors['gpu_layers']}
            note="-1 = all layers to GPU, 0 = CPU only. Leave blank for automatic. Changing this requires a runtime restart."
          >
            <input
              aria-label="gpu layers"
              type="number"
              min={-1}
              max={256}
              step={1}
              placeholder="auto"
              value={form.gpu_layers}
              onChange={(e) => handleFieldChange('gpu_layers', e.target.value)}
              style={inputStyle}
            />
          </FieldRow>

          <FieldRow
            label="CPU threads"
            error={fieldErrors['threads']}
            note="Number of CPU threads for inference (1–64). Leave blank for automatic."
          >
            <input
              aria-label="cpu threads"
              type="number"
              min={1}
              max={64}
              step={1}
              placeholder="auto"
              value={form.threads}
              onChange={(e) => handleFieldChange('threads', e.target.value)}
              style={inputStyle}
            />
          </FieldRow>

          <FieldRow
            label="Temperature"
            error={fieldErrors['temperature']}
            note="Sampling randomness (0.0–2.0). Higher = more creative. Leave blank for runtime default."
          >
            <input
              aria-label="temperature"
              type="number"
              min={0}
              max={2}
              step={0.05}
              placeholder="runtime default"
              value={form.temperature}
              onChange={(e) => handleFieldChange('temperature', e.target.value)}
              style={inputStyle}
            />
          </FieldRow>

          <FieldRow
            label="Top-P"
            error={fieldErrors['top_p']}
            note="Nucleus sampling threshold (0.0–1.0). Leave blank for runtime default."
          >
            <input
              aria-label="top-p"
              type="number"
              min={0}
              max={1}
              step={0.05}
              placeholder="runtime default"
              value={form.top_p}
              onChange={(e) => handleFieldChange('top_p', e.target.value)}
              style={inputStyle}
            />
          </FieldRow>

          <FieldRow
            label="Repeat penalty"
            error={fieldErrors['repeat_penalty']}
            note="Penalty for repeated tokens (1.0–2.0). Leave blank for runtime default."
          >
            <input
              aria-label="repeat penalty"
              type="number"
              min={1}
              max={2}
              step={0.05}
              placeholder="runtime default"
              value={form.repeat_penalty}
              onChange={(e) => handleFieldChange('repeat_penalty', e.target.value)}
              style={inputStyle}
            />
          </FieldRow>

          {requiresRestart && (
            <div
              role="status"
              aria-label="restart required"
              style={{
                background: 'rgba(251,191,36,0.08)',
                border: '1px solid rgba(251,191,36,0.3)',
                borderRadius: '6px',
                padding: '0.6rem 0.75rem',
                marginBottom: '0.75rem',
                fontSize: '0.875rem',
                color: '#fcd34d',
              }}
            >
              Context length and GPU layer changes require restarting the runtime to take effect.
            </div>
          )}

          {advApplyError && <ApiErrorView error={advApplyError} compact context="RuntimeSettingsPanel-AdvApply" />}
          {resetError && <ApiErrorView error={resetError} compact context="RuntimeSettingsPanel-Reset" />}

          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            <button
              aria-label="apply advanced settings"
              onClick={handleAdvancedApply}
              disabled={advApplying}
              style={{ ...primaryBtnStyle, cursor: advApplying ? 'wait' : 'pointer' }}
            >
              {advApplying ? 'Applying…' : 'Apply'}
            </button>
            <button
              aria-label="reset to defaults"
              onClick={handleReset}
              disabled={resetting}
              style={{ ...btnStyle, cursor: resetting ? 'wait' : 'pointer' }}
            >
              {resetting ? 'Resetting…' : 'Reset to defaults'}
            </button>
            <a
              href={DOCS_URL}
              target="_blank"
              rel="noreferrer"
              aria-label="troubleshooting docs"
              style={{
                fontSize: '0.8rem',
                color: '#71717a',
                display: 'flex',
                alignItems: 'center',
                textDecoration: 'underline',
              }}
            >
              Troubleshooting docs ↗
            </a>
          </div>
        </div>
      )}
    </div>
  )
}
