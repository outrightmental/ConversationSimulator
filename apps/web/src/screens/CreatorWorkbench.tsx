// SPDX-License-Identifier: Apache-2.0
import { useState, useEffect, useCallback, useRef, type CSSProperties } from 'react'
import { useBlocker } from 'react-router-dom'
import { FormEditor } from '@convsim/ui'
import type { PackFileType } from '@convsim/scenario-schema'
import { api, type WorkbenchPack, type FileNode, type WorkbenchValidation, type WorkbenchValidationIssue, type WorkbenchImportValidationError } from '../api/client'

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

function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

// ---------------------------------------------------------------------------
// PackList
// ---------------------------------------------------------------------------

interface PackListProps {
  packs: WorkbenchPack[]
  selected: WorkbenchPack | null
  onSelect: (pack: WorkbenchPack) => void
  onImport: (file: File) => void
  importing: boolean
  importError: string | null
  importValidation: WorkbenchImportValidationError | null
  importRenamed: string | null
}

function PackList({ packs, selected, onSelect, onImport, importing, importError, importValidation, importRenamed }: PackListProps) {
  const official = packs.filter((p) => p.kind === 'official')
  const localDev = packs.filter((p) => p.kind === 'local-dev')
  const fileInputRef = useRef<HTMLInputElement>(null)

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

  return (
    <div>
      {packs.length === 0 && (
        <p style={{ fontSize: '0.85rem', color: '#52525b', padding: '0.5rem 0.75rem' }}>
          No packs found.
        </p>
      )}
      {group('Official', official)}
      {group('Local Dev', localDev)}

      {/* Import button */}
      <div style={{ padding: '0.4rem 0.75rem', borderTop: '1px solid rgba(255,255,255,0.06)', marginTop: '0.25rem' }}>
        <input
          ref={fileInputRef}
          type="file"
          accept=".zip"
          data-testid="import-file-input"
          style={{ display: 'none' }}
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) onImport(file)
            // Reset so the same file can be re-imported if needed
            e.target.value = ''
          }}
        />
        <button
          data-testid="import-pack-button"
          disabled={importing}
          onClick={() => fileInputRef.current?.click()}
          style={{ ...BTN, width: '100%', textAlign: 'center', ...(importing ? BTN_DISABLED : {}) }}
          aria-label={importing ? 'Importing…' : 'Import pack from .zip'}
        >
          {importing ? 'Importing…' : '⬆ Import Pack (.zip)'}
        </button>

        {importError && (
          <p role="alert" data-testid="import-error" style={{ fontSize: '0.75rem', color: '#f87171', marginTop: '0.4rem' }}>
            {importError}
          </p>
        )}

        {importRenamed && !importError && (
          <p data-testid="import-renamed-notice" style={{ fontSize: '0.75rem', color: '#fbbf24', marginTop: '0.4rem' }}>
            Imported as "{importRenamed}" (existing pack with that ID was kept).
          </p>
        )}

        {importValidation && !importError && (
          <div data-testid="import-validation-errors" role="alert" style={{ fontSize: '0.75rem', color: '#f87171', marginTop: '0.4rem' }}>
            <strong>Import rejected — pack is invalid:</strong>
            <ul style={{ margin: '0.25rem 0 0', paddingLeft: '1rem' }}>
              {importValidation.errors.slice(0, 5).map((e, i) => (
                <li key={i}>{e.file ? `${e.file}: ` : ''}{e.message}</li>
              ))}
              {importValidation.errors.length > 5 && (
                <li>…and {importValidation.errors.length - 5} more error(s)</li>
              )}
            </ul>
          </div>
        )}
      </div>
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

function detectPackFileType(filePath: string): PackFileType | null {
  const parts = filePath.split('/')
  const name = parts[parts.length - 1] ?? ''
  if (name === 'manifest.yaml' || name === 'manifest.yml') return 'manifest'
  if (parts.length >= 2 && (name.endsWith('.yaml') || name.endsWith('.yml'))) {
    const dir = parts[parts.length - 2]
    if (dir === 'scenarios') return 'scenario'
    if (dir === 'npcs') return 'npc'
    if (dir === 'rubrics') return 'rubric'
  }
  return null
}

interface FileEditorProps {
  filePath: string
  content: string
  editable: boolean
  isDirty: boolean
  saving: boolean
  saveError: string | null
  copying: boolean
  copyError: string | null
  fileType: PackFileType | null
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
  fileType,
  onChange,
  onSave,
  onCopyToLocal,
}: FileEditorProps) {
  const ext = filePath.split('.').pop()?.toLowerCase() ?? ''
  const isMarkdown = ext === 'md'
  const [editorMode, setEditorMode] = useState<'yaml' | 'form'>('yaml')

  useEffect(() => {
    setEditorMode('yaml')
  }, [filePath])

  const canUseFormEditor = editable && fileType !== null

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

        {canUseFormEditor && (
          <div
            data-testid="editor-mode-toggle"
            style={{ display: 'flex', border: '1px solid rgba(255,255,255,0.12)', borderRadius: '4px', overflow: 'hidden' }}
          >
            <button
              data-testid="editor-mode-yaml"
              onClick={() => setEditorMode('yaml')}
              aria-pressed={editorMode === 'yaml'}
              aria-label="YAML editor mode"
              style={{
                ...BTN,
                padding: '0.15rem 0.5rem',
                border: 'none',
                borderRadius: 0,
                background: editorMode === 'yaml' ? 'rgba(99,102,241,0.2)' : 'transparent',
                color: editorMode === 'yaml' ? '#a5b4fc' : '#71717a',
              }}
            >
              YAML
            </button>
            <button
              data-testid="editor-mode-form"
              onClick={() => setEditorMode('form')}
              aria-pressed={editorMode === 'form'}
              aria-label="Form editor mode"
              style={{
                ...BTN,
                padding: '0.15rem 0.5rem',
                border: 'none',
                borderLeft: '1px solid rgba(255,255,255,0.12)',
                borderRadius: 0,
                background: editorMode === 'form' ? 'rgba(99,102,241,0.2)' : 'transparent',
                color: editorMode === 'form' ? '#a5b4fc' : '#71717a',
              }}
            >
              Form
            </button>
          </div>
        )}

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

      {/* Editor — form mode for recognized YAML types, raw textarea otherwise */}
      {editorMode === 'form' && canUseFormEditor ? (
        <div style={{ flex: 1, overflow: 'auto', padding: '0.75rem' }}>
          <FormEditor
            fileType={fileType}
            initialYaml={content}
            onChange={onChange}
          />
        </div>
      ) : (
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
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// ValidationPanel — pack-level validation status, refreshed after each save
// ---------------------------------------------------------------------------

const SECURITY_RULES = new Set(['FORBIDDEN_FILE', 'FORBIDDEN_BINARY'])

// Authoring documentation the suggested fixes refer to ("See the authoring
// guide"). Surfaced as links so creators can reach them without leaving the
// workbench.
const AUTHORING_DOCS_URL = 'https://github.com/outrightmental/ConversationSimulator/blob/main/docs/scenario-authoring.md'
const VALIDATION_DOCS_URL = 'https://github.com/outrightmental/ConversationSimulator/blob/main/docs/pack-validation.md'

function isSecurityIssue(issue: WorkbenchValidationIssue): boolean {
  return SECURITY_RULES.has(issue.rule_id) || issue.category === 'security'
}

// Group a flat issue list by file path.
function groupByFile(issues: WorkbenchValidationIssue[]): Map<string, WorkbenchValidationIssue[]> {
  const map = new Map<string, WorkbenchValidationIssue[]>()
  for (const issue of issues) {
    const key = issue.file || '(pack-wide)'
    const arr = map.get(key) ?? []
    arr.push(issue)
    map.set(key, arr)
  }
  return map
}

interface ValidationPanelProps {
  validation: WorkbenchValidation | null
  loading: boolean
  serviceError: string | null
  onSelectFile?: (filePath: string) => void
  onRefresh?: () => void
}

function ValidationPanel({ validation, loading, serviceError, onSelectFile, onRefresh }: ValidationPanelProps) {
  const [copied, setCopied] = useState(false)

  function handleCopy() {
    if (!validation) return
    const lines = [
      `Validation: ${validation.valid ? 'PASS' : 'FAIL'}`,
      ...validation.errors.map((e) => `[ERROR] ${e.file || '(pack-wide)'}${e.pointer ? ' ' + e.pointer : ''}: ${e.message} (${e.rule_id})`),
      ...validation.warnings.map((w) => `[WARNING] ${w.file || '(pack-wide)'}${w.pointer ? ' ' + w.pointer : ''}: ${w.message} (${w.rule_id})`),
    ]
    void navigator.clipboard.writeText(lines.join('\n'))
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const panelBase: CSSProperties = {
    fontSize: '0.8rem',
    margin: '0 0 1rem',
    padding: '0.5rem 0.75rem',
    borderRadius: '4px',
  }

  if (loading) {
    return (
      <p data-testid="validation-panel" style={{ fontSize: '0.8rem', color: '#71717a', margin: '0 0 1rem' }}>
        Validating pack…
      </p>
    )
  }

  // Service error — validator is unavailable, not a pack issue
  if (serviceError) {
    return (
      <div
        data-testid="validation-panel"
        role="alert"
        style={{
          ...panelBase,
          border: '1px solid rgba(251,191,36,0.3)',
          background: 'rgba(251,191,36,0.06)',
          display: 'flex',
          alignItems: 'center',
          gap: '0.75rem',
        }}
      >
        <span style={{ color: '#fbbf24' }}>⚠ Validator unavailable</span>
        <span style={{ color: '#71717a', flex: 1 }}>{serviceError}</span>
        {onRefresh && (
          <button
            onClick={onRefresh}
            style={{ ...BTN, fontSize: '0.75rem', padding: '0.2rem 0.5rem' }}
            aria-label="Retry validation"
          >
            Retry
          </button>
        )}
      </div>
    )
  }

  if (!validation) return null

  const errorCount = validation.errors.length
  const warningCount = validation.warnings.length

  if (validation.valid && warningCount === 0) {
    return (
      <div
        data-testid="validation-panel"
        role="status"
        style={{
          ...panelBase,
          border: '1px solid rgba(74,222,128,0.2)',
          background: 'rgba(74,222,128,0.05)',
          display: 'flex',
          alignItems: 'center',
          gap: '0.75rem',
        }}
      >
        <span style={{ color: '#4ade80' }}>✓ Pack is valid</span>
        {onRefresh && (
          <button
            onClick={onRefresh}
            style={{ ...BTN, fontSize: '0.75rem', padding: '0.2rem 0.5rem', marginLeft: 'auto' }}
            aria-label="Revalidate pack"
          >
            Revalidate
          </button>
        )}
      </div>
    )
  }

  const allIssues = [...validation.errors, ...validation.warnings]
  const byFile = groupByFile(allIssues)
  const hasSecurityIssues = allIssues.some(isSecurityIssue)

  const headerColor = errorCount > 0 ? '#f87171' : '#fbbf24'
  const borderColor = hasSecurityIssues
    ? 'rgba(239,68,68,0.4)'
    : errorCount > 0
    ? 'rgba(248,113,113,0.25)'
    : 'rgba(251,191,36,0.25)'
  const bgColor = hasSecurityIssues
    ? 'rgba(239,68,68,0.06)'
    : errorCount > 0
    ? 'rgba(248,113,113,0.04)'
    : 'rgba(251,191,36,0.06)'

  return (
    <div
      data-testid="validation-panel"
      role="status"
      style={{
        ...panelBase,
        border: `1px solid ${borderColor}`,
        background: bgColor,
      }}
    >
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
        <span style={{ color: headerColor, fontWeight: 600 }}>
          {errorCount > 0 && `${errorCount} validation error${errorCount === 1 ? '' : 's'}`}
          {errorCount > 0 && warningCount > 0 && ', '}
          {warningCount > 0 && `${warningCount} warning${warningCount === 1 ? '' : 's'}`}
        </span>
        {hasSecurityIssues && (
          <span
            data-testid="security-badge"
            style={{
              fontSize: '0.7rem',
              fontWeight: 700,
              background: 'rgba(239,68,68,0.2)',
              border: '1px solid rgba(239,68,68,0.5)',
              borderRadius: '3px',
              padding: '0.1rem 0.4rem',
              color: '#fca5a5',
              letterSpacing: '0.03em',
            }}
          >
            ⛔ SECURITY
          </span>
        )}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: '0.4rem' }}>
          <button
            onClick={handleCopy}
            data-testid="copy-validation-button"
            style={{ ...BTN, fontSize: '0.72rem', padding: '0.15rem 0.5rem' }}
            aria-label="Copy validation output"
          >
            {copied ? '✓ Copied' : 'Copy'}
          </button>
          {onRefresh && (
            <button
              onClick={onRefresh}
              style={{ ...BTN, fontSize: '0.72rem', padding: '0.15rem 0.5rem' }}
              aria-label="Revalidate pack"
            >
              Revalidate
            </button>
          )}
        </div>
      </div>

      {/* Issues grouped by file */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        {Array.from(byFile.entries()).map(([file, issues]) => {
          const fileHasSecurity = issues.some(isSecurityIssue)
          const isClickable = onSelectFile !== undefined && /\.(yaml|yml|md|txt)$/.test(file)

          return (
            <div key={file}>
              {/* File header — clickable when the file can be opened in the editor */}
              {isClickable ? (
                <button
                  onClick={() => onSelectFile(file)}
                  data-testid={`validation-file-link-${file}`}
                  style={{
                    background: 'none',
                    border: 'none',
                    padding: '0',
                    cursor: 'pointer',
                    color: fileHasSecurity ? '#fca5a5' : '#a1a1aa',
                    fontSize: '0.78rem',
                    fontFamily: 'monospace',
                    textDecoration: 'underline',
                    textUnderlineOffset: '2px',
                    marginBottom: '0.2rem',
                  }}
                  aria-label={`Open ${file}`}
                >
                  📄 {file}
                </button>
              ) : (
                <span
                  style={{
                    color: fileHasSecurity ? '#fca5a5' : '#71717a',
                    fontSize: '0.78rem',
                    fontFamily: 'monospace',
                    display: 'block',
                    marginBottom: '0.2rem',
                  }}
                >
                  {file === '(pack-wide)' ? '⬛ (pack-wide)' : `📄 ${file}`}
                </span>
              )}

              {/* Individual findings for this file */}
              <ul style={{ margin: 0, paddingLeft: '1rem', display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
                {issues.map((issue, i) => {
                  const isSec = isSecurityIssue(issue)
                  const issueColor = issue.severity === 'error' ? '#fca5a5' : '#fcd34d'

                  return (
                    <li
                      key={`${issue.rule_id}-${issue.file}-${issue.pointer}-${i}`}
                      style={{ color: issueColor, lineHeight: 1.4 }}
                    >
                      <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'baseline', flexWrap: 'wrap' }}>
                        {isSec && (
                          <span
                            style={{
                              fontSize: '0.68rem',
                              fontWeight: 700,
                              background: 'rgba(239,68,68,0.25)',
                              borderRadius: '2px',
                              padding: '0.05rem 0.3rem',
                              color: '#fca5a5',
                              flexShrink: 0,
                            }}
                          >
                            SECURITY
                          </span>
                        )}
                        {issue.pointer && issue.pointer !== '(root)' && (
                          <code style={{ color: '#71717a', fontSize: '0.75rem' }}>{issue.pointer}</code>
                        )}
                        <span>{issue.message}</span>
                        <code
                          style={{
                            fontSize: '0.68rem',
                            color: '#3f3f46',
                            background: 'rgba(255,255,255,0.04)',
                            borderRadius: '2px',
                            padding: '0.05rem 0.25rem',
                          }}
                        >
                          {issue.rule_id}
                        </code>
                      </div>
                      {issue.suggested_fix && (
                        <div
                          data-testid={`suggested-fix-${i}`}
                          style={{
                            fontSize: '0.75rem',
                            color: '#6b7280',
                            marginTop: '0.15rem',
                            paddingLeft: '0.1rem',
                          }}
                        >
                          → {issue.suggested_fix}
                        </div>
                      )}
                    </li>
                  )
                })}
              </ul>
            </div>
          )
        })}
      </div>

      {/* Links to authoring docs referenced by the suggested fixes */}
      <div style={{ marginTop: '0.6rem', fontSize: '0.72rem', color: '#71717a', display: 'flex', gap: '0.9rem' }}>
        <a href={AUTHORING_DOCS_URL} target="_blank" rel="noreferrer" style={{ color: '#93c5fd' }}>
          Authoring guide ↗
        </a>
        <a href={VALIDATION_DOCS_URL} target="_blank" rel="noreferrer" style={{ color: '#93c5fd' }}>
          Validation rules ↗
        </a>
      </div>
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
          aria-hidden="true"
          style={{ width: '6px', height: '6px', borderRadius: '50%', background: statusColor, flexShrink: 0 }}
        />
        <span
          role="status"
          aria-live="polite"
          aria-atomic="true"
          style={{ fontSize: '0.8rem', color: statusColor, flex: 1 }}
        >
          {statusLabel}
        </span>
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
          role="log"
          aria-label="Test chat transcript"
          aria-live="polite"
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
          role="group"
          aria-label="NPC state variables"
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
                  role="meter"
                  aria-label={`${key.replace(/_/g, ' ')}: ${value} out of 100`}
                  aria-valuenow={value}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  style={{
                    height: '4px',
                    background: 'rgba(255,255,255,0.1)',
                    borderRadius: '2px',
                    overflow: 'hidden',
                  }}
                >
                  <div
                    aria-hidden="true"
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
            aria-label="Test chat message"
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
  const [validationServiceError, setValidationServiceError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'edit' | 'test'>('edit')
  // Import state
  const [importing, setImporting] = useState(false)
  const [importError, setImportError] = useState<string | null>(null)
  const [importValidation, setImportValidation] = useState<WorkbenchImportValidationError | null>(null)
  const [importRenamed, setImportRenamed] = useState<string | null>(null)
  // Export state
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)
  const [exportFilename, setExportFilename] = useState<string | null>(null)

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

  // Refresh the pack's validation state. Surfaces service errors (network
  // failures, unexpected backend responses) separately from pack findings so
  // creators can distinguish "my pack has issues" from "the validator is down".
  const refreshValidation = useCallback(async (pack: WorkbenchPack) => {
    setValidationLoading(true)
    setValidationServiceError(null)
    try {
      const result = await api.workbench.validate(pack.kind, pack.slug)
      if (isValidation(result)) {
        setValidation(result)
      } else {
        setValidation(null)
        setValidationServiceError('Validator returned an unexpected response.')
      }
    } catch (e: unknown) {
      setValidation(null)
      setValidationServiceError(e instanceof Error ? e.message : 'Validation service error.')
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
    setExportError(null)
    setExportFilename(null)
    setImportError(null)
    setImportValidation(null)
    setImportRenamed(null)
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
        // The save re-validated successfully, so any earlier service error is
        // stale — clear it so it doesn't mask the fresh result (the service-error
        // branch of ValidationPanel renders ahead of the validation branch).
        setValidationServiceError(null)
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

  async function handleImport(file: File) {
    setImporting(true)
    setImportError(null)
    setImportValidation(null)
    setImportRenamed(null)
    try {
      const result = await api.workbench.importPack(file)
      if (result.kind === 'validation') {
        setImportValidation(result)
        return
      }
      // Success: add the new pack to the list and select it
      const newPack: WorkbenchPack = {
        kind: result.kind,
        slug: result.slug,
        pack_id: result.pack_id,
        name: result.name,
        editable: result.editable,
      }
      setPacks((prev) => [...prev.filter((p) => !(p.kind === newPack.kind && p.slug === newPack.slug)), newPack])
      // Select the new pack first: handleSelectPack resets the import notices,
      // so the rename notice must be set *after* it or it would be cleared.
      await handleSelectPack(newPack)
      if (result.renamed_from) {
        setImportRenamed(result.slug)
      }
    } catch (e: unknown) {
      setImportError(e instanceof Error ? e.message : 'Failed to import pack')
    } finally {
      setImporting(false)
    }
  }

  async function handleExport() {
    if (!selectedPack) return
    setExporting(true)
    setExportError(null)
    setExportFilename(null)
    try {
      const { blob, filename } = await api.workbench.exportPack(selectedPack.kind, selectedPack.slug)
      triggerDownload(blob, filename)
      setExportFilename(filename)
    } catch (e: unknown) {
      setExportError(e instanceof Error ? e.message : 'Failed to export pack')
    } finally {
      setExporting(false)
    }
  }

  return (
    <div>
      <h1 style={{ marginBottom: '0.25rem' }}>Creator Workbench</h1>
      <p style={{ color: '#71717a', fontSize: '0.875rem', marginBottom: '1.5rem' }}>
        Inspect and edit scenario packs. Official packs are read-only — create a local copy to modify them.{' '}
        <a href={AUTHORING_DOCS_URL} target="_blank" rel="noreferrer" style={{ color: '#93c5fd' }}>
          Creator guide ↗
        </a>
      </p>

      {packsError && (
        <p role="alert" style={{ fontSize: '0.875rem', color: '#f87171', marginBottom: '1rem' }}>
          Could not load packs: {packsError}
        </p>
      )}

      {selectedPack && (
        <ValidationPanel
          validation={validation}
          loading={validationLoading}
          serviceError={validationServiceError}
          onSelectFile={handleSelectFile}
          onRefresh={() => { void refreshValidation(selectedPack) }}
        />
      )}

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
            <PackList
              packs={packs}
              selected={selectedPack}
              onSelect={handleSelectPack}
              onImport={handleImport}
              importing={importing}
              importError={importError}
              importValidation={importValidation}
              importRenamed={importRenamed}
            />
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
                alignItems: 'center',
                borderBottom: '1px solid rgba(255,255,255,0.08)',
                background: 'rgba(0,0,0,0.1)',
                flexShrink: 0,
              }}
            >
              <div role="tablist" aria-label="Workbench panels" style={{ display: 'flex' }}>
              {(['edit', 'test'] as const).map((tab) => (
                <button
                  key={tab}
                  role="tab"
                  id={`workbench-tab-${tab}`}
                  aria-controls={`workbench-panel-${tab}`}
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

              {/* Export controls — pushed to the right */}
              <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0 0.5rem' }}>
                {exportFilename && !exportError && (
                  <span
                    data-testid="export-success"
                    style={{ fontSize: '0.72rem', color: '#4ade80' }}
                  >
                    ✓ {exportFilename}
                  </span>
                )}
                {exportError && (
                  <span
                    data-testid="export-error"
                    role="alert"
                    style={{ fontSize: '0.72rem', color: '#f87171', maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                    title={exportError}
                  >
                    {exportError}
                  </span>
                )}
                <button
                  data-testid="export-pack-button"
                  onClick={() => { void handleExport() }}
                  disabled={exporting}
                  style={{
                    ...BTN,
                    fontSize: '0.75rem',
                    padding: '0.25rem 0.6rem',
                    ...(exporting ? BTN_DISABLED : {}),
                  }}
                  aria-label={exporting ? 'Exporting…' : 'Export pack as .zip'}
                >
                  {exporting ? 'Exporting…' : '⬇ Export .zip'}
                </button>
              </div>
            </div>
          )}

          {/* Edit panel */}
          <div
            id="workbench-panel-edit"
            role="tabpanel"
            aria-labelledby="workbench-tab-edit"
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
                fileType={detectPackFileType(selectedFile)}
                onChange={setEditorContent}
                onSave={handleSave}
                onCopyToLocal={!editorEditable ? handleCopyToLocal : undefined}
              />
            )}
          </div>

          {/* Test chat panel — keeps session alive while editing (display:none, not unmounted) */}
          {selectedPack && (
            <div
              id="workbench-panel-test"
              role="tabpanel"
              aria-labelledby="workbench-tab-test"
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
