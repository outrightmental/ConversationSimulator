// SPDX-License-Identifier: Apache-2.0
import { useState, useEffect, useCallback, useRef, type CSSProperties } from 'react'
import { useBlocker } from 'react-router-dom'
import { api, type WorkbenchPack, type FileNode, type WorkbenchValidation } from '../api/client'

// A validation response is only usable if it carries the expected error/warning
// arrays. Backends without a validator (or unexpected shapes) are treated as
// "no validation available" rather than crashing the screen.
function isValidation(v: unknown): v is WorkbenchValidation {
  return (
    typeof v === 'object' &&
    v !== null &&
    typeof (v as WorkbenchValidation).valid === 'boolean' &&
    Array.isArray((v as WorkbenchValidation).errors) &&
    Array.isArray((v as WorkbenchValidation).warnings)
  )
}

// useBlocker requires a data router. Production uses createBrowserRouter (see main.tsx)
// which provides this. Tests and Storybook use MemoryRouter which does not, so the
// hook throws there — the try-catch degrades gracefully to a no-op blocker.
function useSafeBlocker(when: boolean) {
  try {
    return useBlocker(when)
  } catch {
    return { state: 'unblocked' as const, proceed: undefined, reset: undefined }
  }
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const PANEL_STYLE: CSSProperties = {
  background: 'rgba(255,255,255,0.03)',
  border: '1px solid rgba(255,255,255,0.08)',
  borderRadius: '6px',
  overflow: 'auto',
}

const BTN: CSSProperties = {
  padding: '0.35rem 0.8rem',
  borderRadius: '4px',
  border: '1px solid rgba(255,255,255,0.15)',
  cursor: 'pointer',
  background: 'transparent',
  color: '#e8e8ea',
  fontSize: '0.8rem',
}

const BTN_PRIMARY: CSSProperties = {
  ...BTN,
  background: 'rgba(99,102,241,0.2)',
  border: '1px solid rgba(99,102,241,0.5)',
  color: '#a5b4fc',
}

const BTN_DISABLED: CSSProperties = {
  opacity: 0.45,
  cursor: 'not-allowed',
}

// ---------------------------------------------------------------------------
// PackList
// ---------------------------------------------------------------------------

interface PackListProps {
  packs: WorkbenchPack[]
  selected: WorkbenchPack | null
  onSelect: (pack: WorkbenchPack) => void
}

function PackList({ packs, selected, onSelect }: PackListProps) {
  const official = packs.filter((p) => p.kind === 'official')
  const localDev = packs.filter((p) => p.kind === 'local-dev')

  function group(label: string, items: WorkbenchPack[]) {
    if (items.length === 0) return null
    return (
      <div style={{ marginBottom: '0.75rem' }}>
        <div style={{ fontSize: '0.7rem', fontWeight: 600, color: '#71717a', textTransform: 'uppercase', letterSpacing: '0.06em', padding: '0.25rem 0.75rem' }}>
          {label}
        </div>
        {items.map((p) => {
          const isSelected = selected?.kind === p.kind && selected.slug === p.slug
          return (
            <button
              key={`${p.kind}/${p.slug}`}
              onClick={() => onSelect(p)}
              style={{
                display: 'block',
                width: '100%',
                textAlign: 'left',
                padding: '0.4rem 0.75rem',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                background: isSelected ? 'rgba(99,102,241,0.15)' : 'transparent',
                color: isSelected ? '#a5b4fc' : '#d4d4d8',
                fontSize: '0.85rem',
                fontWeight: isSelected ? 600 : 400,
              }}
              aria-pressed={isSelected}
            >
              <span>{p.name ?? p.slug}</span>
              {!p.editable && (
                <span style={{ fontSize: '0.7rem', color: '#52525b', marginLeft: '0.4rem' }}>
                  official
                </span>
              )}
            </button>
          )
        })}
      </div>
    )
  }

  if (packs.length === 0) {
    return (
      <p style={{ fontSize: '0.85rem', color: '#52525b', padding: '0.5rem 0.75rem' }}>
        No packs found.
      </p>
    )
  }

  return (
    <div>
      {group('Official', official)}
      {group('Local Dev', localDev)}
    </div>
  )
}

// ---------------------------------------------------------------------------
// FileTree
// ---------------------------------------------------------------------------

const FILE_ICONS: Record<string, string> = {
  yaml: '📄',
  markdown: '📝',
  text: '📃',
  dir: '📁',
  other: '📎',
}

interface FileTreeProps {
  nodes: FileNode[]
  selected: string | null
  onSelect: (path: string, kind: FileNode['kind']) => void
  depth?: number
}

function FileTree({ nodes, selected, onSelect, depth = 0 }: FileTreeProps) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())

  function toggleDir(path: string) {
    setCollapsed((prev) => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }

  return (
    <ul
      role={depth === 0 ? 'tree' : 'group'}
      aria-label={depth === 0 ? 'Pack files' : undefined}
      style={{ listStyle: 'none', padding: 0, margin: 0 }}
    >
      {nodes.map((node) => {
        const isDir = node.kind === 'dir'
        const isSelected = selected === node.path
        const isCollapsed = collapsed.has(node.path)
        const isEditable = node.kind === 'yaml' || node.kind === 'markdown' || node.kind === 'text'
        const icon = FILE_ICONS[node.kind] ?? '📎'

        return (
          <li
            key={node.path}
            role="treeitem"
            aria-selected={isSelected}
            aria-expanded={isDir ? !isCollapsed : undefined}
            style={{ paddingLeft: `${depth * 0.875}rem` }}
          >
            <button
              onClick={() => {
                if (isDir) {
                  toggleDir(node.path)
                } else if (isEditable) {
                  onSelect(node.path, node.kind)
                }
              }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.35rem',
                width: '100%',
                textAlign: 'left',
                padding: '0.25rem 0.5rem',
                border: 'none',
                borderRadius: '3px',
                cursor: isDir || isEditable ? 'pointer' : 'default',
                background: isSelected ? 'rgba(99,102,241,0.15)' : 'transparent',
                color: isSelected ? '#a5b4fc' : isEditable ? '#d4d4d8' : '#52525b',
                fontSize: '0.8rem',
                fontFamily: 'inherit',
              }}
              aria-label={`${isDir ? (isCollapsed ? 'Expand' : 'Collapse') : 'Open'} ${node.name}`}
            >
              <span>{isDir ? (isCollapsed ? '▶' : '▼') : icon}</span>
              <span>{node.name}</span>
              {node.kind === 'other' && (
                <span style={{ fontSize: '0.7rem', color: '#3f3f46', marginLeft: 'auto' }}>
                  unsupported
                </span>
              )}
            </button>
            {isDir && !isCollapsed && node.children && node.children.length > 0 && (
              <FileTree
                nodes={node.children}
                selected={selected}
                onSelect={onSelect}
                depth={depth + 1}
              />
            )}
          </li>
        )
      })}
    </ul>
  )
}

// ---------------------------------------------------------------------------
// FileEditor
// ---------------------------------------------------------------------------

interface FileEditorProps {
  filePath: string
  content: string
  editable: boolean
  isDirty: boolean
  saving: boolean
  saveError: string | null
  copying: boolean
  copyError: string | null
  onChange: (v: string) => void
  onSave: () => void
  onCopyToLocal?: () => void
}

function FileEditor({
  filePath,
  content,
  editable,
  isDirty,
  saving,
  saveError,
  copying,
  copyError,
  onChange,
  onSave,
  onCopyToLocal,
}: FileEditorProps) {
  const ext = filePath.split('.').pop()?.toLowerCase() ?? ''
  const isMarkdown = ext === 'md'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Toolbar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          padding: '0.5rem 0.75rem',
          borderBottom: '1px solid rgba(255,255,255,0.08)',
          background: 'rgba(0,0,0,0.15)',
          flexShrink: 0,
        }}
      >
        <code style={{ fontSize: '0.8rem', color: '#a1a1aa', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {filePath}
        </code>

        {!editable && (
          <span
            data-testid="read-only-badge"
            style={{
              fontSize: '0.7rem',
              color: '#fbbf24',
              background: 'rgba(251,191,36,0.1)',
              border: '1px solid rgba(251,191,36,0.25)',
              borderRadius: '3px',
              padding: '0.1rem 0.4rem',
            }}
          >
            Read-only
          </span>
        )}

        {isDirty && (
          <span
            data-testid="dirty-indicator"
            style={{ fontSize: '0.75rem', color: '#fb923c' }}
          >
            Unsaved changes
          </span>
        )}

        {editable && (
          <button
            onClick={onSave}
            disabled={saving || !isDirty}
            data-testid="save-button"
            style={{
              ...BTN_PRIMARY,
              ...(saving || !isDirty ? BTN_DISABLED : {}),
            }}
            aria-label={saving ? 'Saving…' : 'Save file'}
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        )}

        {!editable && onCopyToLocal && (
          <button
            onClick={onCopyToLocal}
            disabled={copying}
            data-testid="copy-to-local-button"
            style={{ ...BTN, ...(copying ? BTN_DISABLED : {}) }}
            aria-label={copying ? 'Copying…' : 'Create local copy to edit'}
          >
            {copying ? 'Copying…' : 'Create local copy to edit'}
          </button>
        )}
      </div>

      {saveError && (
        <p role="alert" style={{ margin: '0.5rem 0.75rem', fontSize: '0.8rem', color: '#f87171' }}>
          Save failed: {saveError}
        </p>
      )}

      {copyError && (
        <p role="alert" style={{ margin: '0.5rem 0.75rem', fontSize: '0.8rem', color: '#f87171' }}>
          Copy failed: {copyError}
        </p>
      )}

      {/* Editor */}
      <textarea
        data-testid="file-editor"
        aria-label={`${isMarkdown ? 'Markdown' : 'YAML'} editor: ${filePath}`}
        readOnly={!editable}
        value={content}
        onChange={(e) => onChange(e.target.value)}
        spellCheck={false}
        style={{
          flex: 1,
          padding: '0.75rem',
          background: editable ? 'rgba(0,0,0,0.3)' : 'rgba(0,0,0,0.15)',
          color: editable ? '#e8e8ea' : '#71717a',
          border: 'none',
          outline: 'none',
          fontFamily: 'monospace',
          fontSize: '0.85rem',
          lineHeight: 1.6,
          resize: 'none',
          cursor: editable ? 'text' : 'default',
        }}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// ValidationPanel — pack-level validation status, refreshed after each save
// ---------------------------------------------------------------------------

interface ValidationPanelProps {
  validation: WorkbenchValidation | null
  loading: boolean
}

function ValidationPanel({ validation, loading }: ValidationPanelProps) {
  if (loading) {
    return (
      <p data-testid="validation-panel" style={{ fontSize: '0.8rem', color: '#71717a', margin: '0 0 1rem' }}>
        Validating pack…
      </p>
    )
  }
  if (!validation) return null

  const errorCount = validation.errors.length
  const warningCount = validation.warnings.length

  if (validation.valid && warningCount === 0) {
    return (
      <p
        data-testid="validation-panel"
        role="status"
        style={{ fontSize: '0.8rem', color: '#4ade80', margin: '0 0 1rem' }}
      >
        ✓ Pack is valid
      </p>
    )
  }

  const issues = [...validation.errors, ...validation.warnings]
  return (
    <div
      data-testid="validation-panel"
      role="status"
      style={{
        fontSize: '0.8rem',
        margin: '0 0 1rem',
        padding: '0.5rem 0.75rem',
        borderRadius: '4px',
        border: '1px solid rgba(251,191,36,0.25)',
        background: 'rgba(251,191,36,0.06)',
      }}
    >
      <div style={{ color: errorCount > 0 ? '#f87171' : '#fbbf24', fontWeight: 600, marginBottom: issues.length ? '0.4rem' : 0 }}>
        {errorCount > 0
          ? `${errorCount} validation error${errorCount === 1 ? '' : 's'}`
          : `${warningCount} validation warning${warningCount === 1 ? '' : 's'}`}
        {errorCount > 0 && warningCount > 0 && `, ${warningCount} warning${warningCount === 1 ? '' : 's'}`}
      </div>
      <ul style={{ margin: 0, paddingLeft: '1.1rem', color: '#a1a1aa' }}>
        {issues.slice(0, 8).map((issue, i) => (
          <li key={`${issue.rule_id}-${issue.file}-${issue.pointer}-${i}`} style={{ color: issue.severity === 'error' ? '#fca5a5' : '#fcd34d' }}>
            <code style={{ color: '#a1a1aa' }}>{issue.file}</code>: {issue.message}
          </li>
        ))}
        {issues.length > 8 && (
          <li style={{ color: '#71717a' }}>…and {issues.length - 8} more</li>
        )}
      </ul>
    </div>
  )
}

// ---------------------------------------------------------------------------
// TestChatPanel — text-only workbench test chat with state inspector
// ---------------------------------------------------------------------------

interface TranscriptEntry {
  role: 'npc' | 'player'
  content: string
  emotion?: string
  stateDelta?: Record<string, number>
  eventFlags?: string[]
  safetyStatus?: string
  endingType?: string | null
}

interface TestChatPanelProps {
  pack: WorkbenchPack
  validation: WorkbenchValidation | null
}

function TestChatPanel({ pack, validation }: TestChatPanelProps) {
  const [chatStatus, setChatStatus] = useState<'idle' | 'starting' | 'active' | 'sending' | 'ended'>('idle')
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([])
  const [stateVars, setStateVars] = useState<Record<string, number>>({})
  const [lastDelta, setLastDelta] = useState<Record<string, number>>({})
  const [inputText, setInputText] = useState('')
  const [endingType, setEndingType] = useState<string | null>(null)
  const [startError, setStartError] = useState<string | null>(null)
  const [turnError, setTurnError] = useState<string | null>(null)
  const sessionIdRef = useRef<string | null>(null)
  const transcriptRef = useRef<HTMLDivElement>(null)

  // Cleanup test session on unmount (pack change or screen exit)
  useEffect(() => {
    return () => {
      if (sessionIdRef.current) {
        api.deleteSession(sessionIdRef.current).catch(() => {})
      }
    }
  }, [])

  // Scroll transcript to bottom on each new entry
  useEffect(() => {
    if (transcriptRef.current) {
      transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight
    }
  }, [transcript])

  const hasValidationErrors = (validation?.errors?.length ?? 0) > 0

  async function startSession() {
    setChatStatus('starting')
    setStartError(null)
    setTranscript([])
    setStateVars({})
    setLastDelta({})
    setEndingType(null)
    setTurnError(null)
    try {
      const result = await api.workbench.startTestSession(pack.kind, pack.slug)
      sessionIdRef.current = result.session_id
      setStateVars(result.state_vars)
      setTranscript([{ role: 'npc', content: result.npc_opening }])
      setChatStatus('active')
    } catch (e) {
      setStartError(e instanceof Error ? e.message : 'Failed to start test session')
      setChatStatus('idle')
    }
  }

  async function handleStart() {
    if (hasValidationErrors) return
    await startSession()
  }

  async function handleDiscard() {
    const id = sessionIdRef.current
    sessionIdRef.current = null
    setChatStatus('idle')
    setTranscript([])
    setStateVars({})
    setLastDelta({})
    setEndingType(null)
    setStartError(null)
    setTurnError(null)
    if (id) {
      try { await api.deleteSession(id) } catch { /* ignore cleanup errors */ }
    }
  }

  async function handleReset() {
    const id = sessionIdRef.current
    sessionIdRef.current = null
    if (id) {
      try { await api.deleteSession(id) } catch { /* ignore */ }
    }
    await startSession()
  }

  async function handleSend() {
    const id = sessionIdRef.current
    if (!id || !inputText.trim() || chatStatus !== 'active') return
    const text = inputText.trim()
    setInputText('')
    setTurnError(null)
    setTranscript(prev => [...prev, { role: 'player', content: text }])
    setChatStatus('sending')
    try {
      const result = await api.submitTurn(id, text)
      const npcEvent = result.events.find(e => e.event_type === 'npc_turn')
      if (npcEvent) {
        const p = npcEvent.payload as Record<string, unknown>
        const delta = (p['state_delta'] as Record<string, number> | undefined) ?? {}
        setLastDelta(delta)
        setStateVars(prev => {
          const next = { ...prev }
          for (const [k, v] of Object.entries(delta)) {
            if (k in next) next[k] = Math.max(0, Math.min(100, (next[k] ?? 0) + v))
          }
          return next
        })
        const npcEntry: TranscriptEntry = {
          role: 'npc',
          content: (p['content'] as string) ?? '',
          emotion: p['emotion'] as string | undefined,
          stateDelta: Object.keys(delta).length > 0 ? delta : undefined,
          eventFlags: ((p['event_flags'] as string[] | undefined) ?? []).filter(Boolean),
          safetyStatus: (p['safety'] as { status?: string } | undefined)?.status,
          endingType: (p['ending_type'] as string | null | undefined) ?? null,
        }
        setTranscript(prev => [...prev, npcEntry])
        if (result.state === 'Ended') {
          setEndingType((p['ending_type'] as string | null | undefined) ?? 'player_exit')
          setChatStatus('ended')
        } else {
          setChatStatus('active')
        }
      }
    } catch (e) {
      setTurnError(e instanceof Error ? e.message : 'Turn failed')
      setChatStatus('active')
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void handleSend()
    }
  }

  // ── Idle / Starting state ──
  if (chatStatus === 'idle' || chatStatus === 'starting') {
    return (
      <div
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '2rem',
          gap: '1rem',
        }}
      >
        <div style={{ fontSize: '0.875rem', color: '#71717a', textAlign: 'center', maxWidth: '320px' }}>
          Start a temporary text-only session to preview conversation flow, state variables, events,
          and safety redirects. Sessions are not saved to history.
        </div>

        {hasValidationErrors && (
          <div
            data-testid="test-chat-validation-error"
            role="alert"
            style={{
              padding: '0.5rem 0.75rem',
              borderRadius: '4px',
              border: '1px solid rgba(248,113,113,0.3)',
              background: 'rgba(248,113,113,0.08)',
              fontSize: '0.8rem',
              color: '#f87171',
              maxWidth: '320px',
            }}
          >
            Fix {validation!.errors.length} validation error
            {validation!.errors.length === 1 ? '' : 's'} before testing.
          </div>
        )}

        {startError && (
          <p
            role="alert"
            data-testid="test-chat-start-error"
            style={{ fontSize: '0.8rem', color: '#f87171', maxWidth: '320px', textAlign: 'center' }}
          >
            {startError}
          </p>
        )}

        <button
          onClick={() => void handleStart()}
          disabled={hasValidationErrors || chatStatus === 'starting'}
          data-testid="start-test-btn"
          style={{
            ...BTN_PRIMARY,
            padding: '0.5rem 1.25rem',
            fontSize: '0.875rem',
            ...(hasValidationErrors || chatStatus === 'starting' ? BTN_DISABLED : {}),
          }}
        >
          {chatStatus === 'starting' ? 'Starting…' : '▶ Start Test Session'}
        </button>
      </div>
    )
  }

  // ── Active / Sending / Ended state ──
  const statusColor =
    chatStatus === 'ended'
      ? endingType === 'success'
        ? '#4ade80'
        : endingType === 'safety_stop'
          ? '#f87171'
          : '#fbbf24'
      : '#4ade80'

  const statusLabel =
    chatStatus === 'ended'
      ? `Ended: ${(endingType ?? 'player_exit').replace(/_/g, ' ')}`
      : chatStatus === 'sending'
        ? 'Thinking…'
        : 'Active'

  const canInteract = chatStatus === 'active' || chatStatus === 'sending'

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* Toolbar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          padding: '0.4rem 0.75rem',
          borderBottom: '1px solid rgba(255,255,255,0.08)',
          background: 'rgba(0,0,0,0.15)',
          flexShrink: 0,
        }}
      >
        <span
          style={{ width: '6px', height: '6px', borderRadius: '50%', background: statusColor, flexShrink: 0 }}
        />
        <span style={{ fontSize: '0.8rem', color: statusColor, flex: 1 }}>{statusLabel}</span>
        {turnError && (
          <span
            data-testid="turn-error"
            role="alert"
            style={{ fontSize: '0.75rem', color: '#f87171' }}
          >
            {turnError}
          </span>
        )}
        <button
          onClick={() => void handleReset()}
          disabled={chatStatus === 'sending'}
          data-testid="reset-test-btn"
          style={{ ...BTN, ...(chatStatus === 'sending' ? BTN_DISABLED : {}) }}
          aria-label="Reset test session"
        >
          Reset
        </button>
        <button
          onClick={() => void handleDiscard()}
          disabled={chatStatus === 'sending'}
          data-testid="discard-test-btn"
          style={{ ...BTN, ...(chatStatus === 'sending' ? BTN_DISABLED : {}) }}
          aria-label="Discard test session"
        >
          Discard
        </button>
      </div>

      {/* Main content: transcript + state inspector */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Transcript */}
        <div
          ref={transcriptRef}
          data-testid="test-transcript"
          style={{
            flex: 2,
            overflowY: 'auto',
            padding: '0.75rem',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.5rem',
          }}
        >
          {transcript.map((entry, i) => (
            <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <div
                style={{
                  alignSelf: entry.role === 'player' ? 'flex-end' : 'flex-start',
                  maxWidth: '82%',
                  padding: '0.5rem 0.75rem',
                  borderRadius: '6px',
                  background:
                    entry.role === 'player'
                      ? 'rgba(99,102,241,0.2)'
                      : 'rgba(255,255,255,0.06)',
                  color: entry.role === 'player' ? '#a5b4fc' : '#e8e8ea',
                  fontSize: '0.85rem',
                  lineHeight: 1.5,
                }}
              >
                {entry.role === 'npc' && entry.emotion && (
                  <div style={{ fontSize: '0.7rem', color: '#71717a', marginBottom: '0.2rem' }}>
                    NPC ({entry.emotion})
                  </div>
                )}
                {entry.content}
              </div>

              {entry.safetyStatus === 'redirect' && (
                <div
                  data-testid="safety-redirect-badge"
                  style={{
                    alignSelf: 'flex-start',
                    fontSize: '0.7rem',
                    color: '#fbbf24',
                    background: 'rgba(251,191,36,0.08)',
                    border: '1px solid rgba(251,191,36,0.2)',
                    borderRadius: '3px',
                    padding: '0.15rem 0.4rem',
                  }}
                >
                  ⚠ Safety redirect applied
                </div>
              )}

              {entry.safetyStatus === 'stop' && (
                <div
                  data-testid="safety-stop-badge"
                  style={{
                    alignSelf: 'flex-start',
                    fontSize: '0.7rem',
                    color: '#f87171',
                    background: 'rgba(248,113,113,0.08)',
                    border: '1px solid rgba(248,113,113,0.2)',
                    borderRadius: '3px',
                    padding: '0.15rem 0.4rem',
                  }}
                >
                  ✕ Safety stop — session ended
                </div>
              )}

              {entry.eventFlags && entry.eventFlags.length > 0 && (
                <div style={{ display: 'flex', gap: '0.25rem', flexWrap: 'wrap' }}>
                  {entry.eventFlags.map((flag) => (
                    <span
                      key={flag}
                      data-testid="event-flag"
                      style={{
                        fontSize: '0.7rem',
                        color: '#a78bfa',
                        background: 'rgba(167,139,250,0.08)',
                        border: '1px solid rgba(167,139,250,0.2)',
                        borderRadius: '3px',
                        padding: '0.1rem 0.35rem',
                      }}
                    >
                      {flag}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}

          {chatStatus === 'ended' && (
            <div
              data-testid="session-ended-banner"
              style={{
                padding: '0.5rem 0.75rem',
                borderRadius: '4px',
                border: `1px solid ${statusColor}33`,
                background: `${statusColor}11`,
                fontSize: '0.8rem',
                color: statusColor,
                textAlign: 'center',
              }}
            >
              Session ended: {(endingType ?? 'player_exit').replace(/_/g, ' ')}
            </div>
          )}
        </div>

        {/* State inspector */}
        <div
          data-testid="state-inspector"
          style={{
            width: '180px',
            flexShrink: 0,
            borderLeft: '1px solid rgba(255,255,255,0.08)',
            padding: '0.75rem 0.5rem',
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.5rem',
          }}
        >
          <div
            style={{
              fontSize: '0.7rem',
              fontWeight: 600,
              color: '#71717a',
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
            }}
          >
            State Variables
          </div>

          {Object.entries(stateVars).map(([key, value]) => {
            const delta = lastDelta[key]
            return (
              <div key={key} style={{ fontSize: '0.8rem' }}>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    marginBottom: '0.15rem',
                  }}
                >
                  <span style={{ color: '#a1a1aa' }}>{key.replace(/_/g, ' ')}</span>
                  <span
                    style={{ color: '#e8e8ea', display: 'flex', gap: '0.3rem', alignItems: 'center' }}
                  >
                    {value}
                    {delta !== undefined && delta !== 0 && (
                      <span
                        data-testid="state-delta"
                        style={{ fontSize: '0.7rem', color: delta > 0 ? '#4ade80' : '#f87171' }}
                      >
                        {delta > 0 ? `+${delta}` : delta}
                      </span>
                    )}
                  </span>
                </div>
                <div
                  style={{
                    height: '4px',
                    background: 'rgba(255,255,255,0.1)',
                    borderRadius: '2px',
                    overflow: 'hidden',
                  }}
                >
                  <div
                    style={{
                      height: '100%',
                      width: `${value}%`,
                      background:
                        value >= 60 ? '#4ade80' : value >= 30 ? '#fbbf24' : '#f87171',
                      borderRadius: '2px',
                      transition: 'width 0.3s ease',
                    }}
                  />
                </div>
              </div>
            )
          })}

          {Object.keys(stateVars).length === 0 && (
            <p style={{ fontSize: '0.75rem', color: '#52525b' }}>No state yet.</p>
          )}
        </div>
      </div>

      {/* Input row */}
      {chatStatus !== 'ended' && (
        <div
          style={{
            display: 'flex',
            gap: '0.5rem',
            padding: '0.5rem 0.75rem',
            borderTop: '1px solid rgba(255,255,255,0.08)',
            background: 'rgba(0,0,0,0.15)',
            flexShrink: 0,
          }}
        >
          <textarea
            data-testid="test-chat-input"
            value={inputText}
            onChange={e => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={!canInteract}
            placeholder="Type a message… (Enter to send, Shift+Enter for new line)"
            rows={2}
            style={{
              flex: 1,
              background: 'rgba(0,0,0,0.2)',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: '4px',
              color: '#e8e8ea',
              padding: '0.4rem 0.5rem',
              fontSize: '0.85rem',
              fontFamily: 'inherit',
              resize: 'none',
              outline: 'none',
              opacity: canInteract ? 1 : 0.5,
            }}
          />
          <button
            onClick={() => void handleSend()}
            disabled={chatStatus !== 'active' || !inputText.trim()}
            data-testid="send-test-btn"
            style={{
              ...BTN_PRIMARY,
              alignSelf: 'flex-end',
              ...(chatStatus !== 'active' || !inputText.trim() ? BTN_DISABLED : {}),
            }}
            aria-label="Send message"
          >
            Send
          </button>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// CreatorWorkbench (main screen)
// ---------------------------------------------------------------------------

export default function CreatorWorkbench() {
  const [packs, setPacks] = useState<WorkbenchPack[]>([])
  const [packsError, setPacksError] = useState<string | null>(null)
  const [selectedPack, setSelectedPack] = useState<WorkbenchPack | null>(null)
  const [fileTree, setFileTree] = useState<FileNode[]>([])
  const [treeLoading, setTreeLoading] = useState(false)
  const [treeError, setTreeError] = useState<string | null>(null)
  const [selectedFile, setSelectedFile] = useState<string | null>(null)
  const [editorContent, setEditorContent] = useState('')
  const [savedContent, setSavedContent] = useState('')
  const [editorEditable, setEditorEditable] = useState(false)
  const [fileLoading, setFileLoading] = useState(false)
  const [fileError, setFileError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [copying, setCopying] = useState(false)
  const [copyError, setCopyError] = useState<string | null>(null)
  const [validation, setValidation] = useState<WorkbenchValidation | null>(null)
  const [validationLoading, setValidationLoading] = useState(false)
  const [activeTab, setActiveTab] = useState<'edit' | 'test'>('edit')

  const isDirty = selectedFile !== null && editorContent !== savedContent

  // Block in-app navigation when there are unsaved edits
  const blocker = useSafeBlocker(isDirty)
  useEffect(() => {
    if (blocker.state === 'blocked') {
      if (window.confirm('You have unsaved changes. Leave this page?')) {
        blocker.proceed?.()
      } else {
        blocker.reset?.()
      }
    }
  }, [blocker])

  // Warn on browser/tab close
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (isDirty) {
        e.preventDefault()
        e.returnValue = ''
      }
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [isDirty])

  // Load pack list on mount
  useEffect(() => {
    api.workbench.listPacks()
      .then((ps) => { setPacks(ps); setPacksError(null) })
      .catch((e: unknown) => setPacksError(e instanceof Error ? e.message : 'Failed to load packs'))
  }, [])

  const loadFileTree = useCallback(async (pack: WorkbenchPack) => {
    setTreeLoading(true)
    setTreeError(null)
    setFileTree([])
    try {
      const { tree } = await api.workbench.listFiles(pack.kind, pack.slug)
      setFileTree(tree)
    } catch (e: unknown) {
      setTreeError(e instanceof Error ? e.message : 'Failed to load file tree')
    } finally {
      setTreeLoading(false)
    }
  }, [])

  // Refresh the pack's validation state. Best-effort: the interim convsim-api
  // backend has no validator, so a failure just clears the panel silently.
  const refreshValidation = useCallback(async (pack: WorkbenchPack) => {
    setValidationLoading(true)
    try {
      const result = await api.workbench.validate(pack.kind, pack.slug)
      setValidation(isValidation(result) ? result : null)
    } catch {
      setValidation(null)
    } finally {
      setValidationLoading(false)
    }
  }, [])

  async function handleSelectPack(pack: WorkbenchPack) {
    if (isDirty && !window.confirm('You have unsaved changes. Discard them?')) return
    setSelectedPack(pack)
    setSelectedFile(null)
    setEditorContent('')
    setSavedContent('')
    setSaveError(null)
    setCopyError(null)
    setValidation(null)
    setActiveTab('edit')
    await Promise.all([loadFileTree(pack), refreshValidation(pack)])
  }

  async function handleSelectFile(filePath: string) {
    if (!selectedPack) return
    if (isDirty && !window.confirm('You have unsaved changes. Discard them?')) return
    setSelectedFile(filePath)
    setEditorContent('')
    setSavedContent('')
    setSaveError(null)
    setCopyError(null)
    setFileError(null)
    setFileLoading(true)
    try {
      const { content, editable } = await api.workbench.readFile(selectedPack.kind, selectedPack.slug, filePath)
      setEditorContent(content)
      setSavedContent(content)
      setEditorEditable(editable)
    } catch (e: unknown) {
      setFileError(e instanceof Error ? e.message : 'Failed to load file')
    } finally {
      setFileLoading(false)
    }
  }

  async function handleSave() {
    if (!selectedPack || !selectedFile) return
    setSaving(true)
    setSaveError(null)
    try {
      const result = await api.workbench.writeFile(selectedPack.kind, selectedPack.slug, selectedFile, editorContent)
      setSavedContent(editorContent)
      // The save re-validates the pack. Prefer the validation the write returned;
      // fall back to a dedicated refresh if the backend omitted it.
      if (isValidation(result.validation)) {
        setValidation(result.validation)
      } else {
        await refreshValidation(selectedPack)
      }
    } catch (e: unknown) {
      setSaveError(e instanceof Error ? e.message : 'Failed to save file')
    } finally {
      setSaving(false)
    }
  }

  async function handleCopyToLocal() {
    if (!selectedPack) return
    setCopying(true)
    setCopyError(null)
    try {
      const newPack = await api.workbench.copyToLocal(selectedPack.kind, selectedPack.slug)
      setPacks((prev) => [...prev.filter((p) => !(p.kind === newPack.kind && p.slug === newPack.slug)), newPack])
      // Switch to the new local-dev copy
      setSelectedPack(newPack)
      setSelectedFile(null)
      setEditorContent('')
      setSavedContent('')
      setValidation(null)
      setActiveTab('edit')
      await Promise.all([loadFileTree(newPack), refreshValidation(newPack)])
    } catch (e: unknown) {
      setCopyError(e instanceof Error ? e.message : 'Failed to copy pack to local-dev')
    } finally {
      setCopying(false)
    }
  }

  return (
    <div>
      <h1 style={{ marginBottom: '0.25rem' }}>Creator Workbench</h1>
      <p style={{ color: '#71717a', fontSize: '0.875rem', marginBottom: '1.5rem' }}>
        Inspect and edit scenario packs. Official packs are read-only — create a local copy to modify them.
      </p>

      {packsError && (
        <p role="alert" style={{ fontSize: '0.875rem', color: '#f87171', marginBottom: '1rem' }}>
          Could not load packs: {packsError}
        </p>
      )}

      {selectedPack && <ValidationPanel validation={validation} loading={validationLoading} />}

      <div style={{ display: 'flex', gap: '1rem', height: 'calc(100vh - 220px)', minHeight: '400px' }}>
        {/* Left panel: pack selector + file tree */}
        <div
          style={{
            width: '220px',
            flexShrink: 0,
            display: 'flex',
            flexDirection: 'column',
            gap: '0.75rem',
          }}
        >
          {/* Pack selector */}
          <div
            data-testid="pack-selector"
            style={{ ...PANEL_STYLE, padding: '0.5rem 0', flexShrink: 0, maxHeight: '45%', overflow: 'auto' }}
          >
            <div style={{ fontSize: '0.7rem', fontWeight: 600, color: '#71717a', textTransform: 'uppercase', letterSpacing: '0.06em', padding: '0.25rem 0.75rem 0.5rem' }}>
              Packs
            </div>
            <PackList packs={packs} selected={selectedPack} onSelect={handleSelectPack} />
          </div>

          {/* File tree */}
          <div
            data-testid="file-tree"
            style={{ ...PANEL_STYLE, padding: '0.5rem 0.25rem', flex: 1, overflow: 'auto' }}
          >
            {!selectedPack && (
              <p style={{ fontSize: '0.8rem', color: '#52525b', padding: '0.5rem' }}>
                Select a pack above.
              </p>
            )}
            {selectedPack && treeLoading && (
              <p style={{ fontSize: '0.8rem', color: '#71717a', padding: '0.5rem' }}>Loading…</p>
            )}
            {selectedPack && treeError && (
              <p role="alert" style={{ fontSize: '0.8rem', color: '#f87171', padding: '0.5rem' }}>
                {treeError}
              </p>
            )}
            {selectedPack && !treeLoading && !treeError && fileTree.length === 0 && (
              <p style={{ fontSize: '0.8rem', color: '#52525b', padding: '0.5rem' }}>
                Empty pack directory.
              </p>
            )}
            {selectedPack && !treeLoading && fileTree.length > 0 && (
              <FileTree
                nodes={fileTree}
                selected={selectedFile}
                onSelect={handleSelectFile}
              />
            )}
          </div>
        </div>

        {/* Right panel: editor / test chat */}
        <div style={{ flex: 1, ...PANEL_STYLE, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          {/* Tab header — only when a pack is selected */}
          {selectedPack && (
            <div
              style={{
                display: 'flex',
                borderBottom: '1px solid rgba(255,255,255,0.08)',
                background: 'rgba(0,0,0,0.1)',
                flexShrink: 0,
              }}
            >
              {(['edit', 'test'] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  data-testid={`tab-${tab}`}
                  aria-selected={activeTab === tab}
                  style={{
                    padding: '0.5rem 0.75rem',
                    background: 'transparent',
                    border: 'none',
                    borderBottom: `2px solid ${activeTab === tab ? '#a5b4fc' : 'transparent'}`,
                    color: activeTab === tab ? '#a5b4fc' : '#71717a',
                    cursor: 'pointer',
                    fontSize: '0.8rem',
                    fontFamily: 'inherit',
                  }}
                >
                  {tab === 'edit' ? 'Edit' : 'Test Chat'}
                </button>
              ))}
            </div>
          )}

          {/* Edit panel */}
          <div
            style={{
              flex: 1,
              display: activeTab === 'edit' ? 'flex' : 'none',
              flexDirection: 'column',
              overflow: 'hidden',
            }}
          >
            {!selectedFile && !fileLoading && (
              <div
                style={{
                  flex: 1,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#52525b',
                  fontSize: '0.875rem',
                }}
              >
                {selectedPack
                  ? 'Select a YAML or Markdown file from the tree.'
                  : 'Select a pack to get started.'}
              </div>
            )}

            {fileLoading && (
              <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#71717a', fontSize: '0.875rem' }}>
                Loading file…
              </div>
            )}

            {fileError && !fileLoading && (
              <div style={{ flex: 1, padding: '1rem' }}>
                <p role="alert" style={{ fontSize: '0.875rem', color: '#f87171' }}>
                  {fileError}
                </p>
              </div>
            )}

            {selectedFile && !fileLoading && !fileError && (
              <FileEditor
                filePath={selectedFile}
                content={editorContent}
                editable={editorEditable}
                isDirty={isDirty}
                saving={saving}
                saveError={saveError}
                copying={copying}
                copyError={copyError}
                onChange={setEditorContent}
                onSave={handleSave}
                onCopyToLocal={!editorEditable ? handleCopyToLocal : undefined}
              />
            )}
          </div>

          {/* Test chat panel — keeps session alive while editing (display:none, not unmounted) */}
          {selectedPack && (
            <div
              key={`${selectedPack.kind}/${selectedPack.slug}`}
              style={{
                flex: 1,
                display: activeTab === 'test' ? 'flex' : 'none',
                flexDirection: 'column',
                overflow: 'hidden',
              }}
            >
              <TestChatPanel pack={selectedPack} validation={validation} />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
