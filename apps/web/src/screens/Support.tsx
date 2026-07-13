// SPDX-License-Identifier: Apache-2.0
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { openExternal } from '../lib/openExternal'
import type { ApiError } from '../api/errors'
import { ApiErrorView } from '../components/ApiErrorView'
import type { PreflightResponse, PreflightCheck, PreflightFixAction } from '@convsim/shared'

const ISSUES_URL = 'https://github.com/outrightmental/ConversationSimulator/issues/new/choose'
const TEMPLATE_BASE = 'https://github.com/outrightmental/ConversationSimulator/issues/new?template='
const BETA_REPORT_TEMPLATE_URL =
  'https://github.com/outrightmental/ConversationSimulator/issues/new?template=beta-report.yml&labels=beta-feedback'
const BETA_GUIDE_URL =
  'https://docs.conversationsimulator.com/project/beta-testing/'

const ISSUE_TEMPLATES = [
  { key: 'bug_report', label: 'Bug report', template: 'bug_report.yml' },
  { key: 'steam_platform_bug', label: 'Steam / platform bug', template: 'steam_platform_bug.yml' },
  { key: 'steam_model_install', label: 'Model install issue', template: 'steam_model_install.yml' },
  { key: 'steam_pack_bug', label: 'Scenario pack bug', template: 'steam_pack_bug.yml' },
  { key: 'model_compatibility', label: 'Model compatibility issue', template: 'model_compatibility.yml' },
  { key: 'stt_issue', label: 'Voice input (STT) issue', template: 'stt_issue.yml' },
  { key: 'tts_issue', label: 'Voice output (TTS) issue', template: 'tts_issue.yml' },
  { key: 'safety_issue', label: 'Safety or content concern', template: 'safety_issue.yml' },
  { key: 'steam_privacy_safety', label: 'Privacy or safety (Steam)', template: 'steam_privacy_safety.yml' },
  { key: 'feature_proposal', label: 'Feature request', template: 'feature_proposal.yml' },
]

// Default manifest shown before the bundle is created (mirrors beta_report.py).
const DEFAULT_MANIFEST = [
  'versions.json — app, Python, and OS versions',
  'system.txt — OS name, release, architecture',
  'config.json — settings (home directory replaced with ~)',
  'preflight.json — runtime / STT / TTS health snapshot',
  'recent_errors.txt — last log lines at WARNING or above (no conversation content)',
  'README.txt — privacy notice',
]

type CrashBundleState = 'idle' | 'creating' | 'done' | 'error'
type BetaReportStep = 'idle' | 'consent' | 'creating' | 'done' | 'error'
type SelfTestState = 'idle' | 'running' | 'done' | 'error'

/** Opens a local folder in the OS file manager via the Tauri shell plugin. */
async function openFolderInShell(folderPath: string): Promise<void> {
  const tauri = (window as { __TAURI__?: { core?: { invoke?: (cmd: string, args?: unknown) => Promise<void> } } }).__TAURI__
  const invoke = tauri?.core?.invoke
  if (!invoke) {
    throw new Error('Desktop shell is unavailable')
  }
  await invoke('plugin:shell|open', { path: folderPath })
}

const STATUS_COLORS: Record<string, string> = {
  pass: '#86efac',
  warn: '#fde68a',
  fail: '#fca5a5',
}

const STATUS_LABELS: Record<string, string> = {
  pass: 'Pass',
  warn: 'Warn',
  fail: 'Fail',
}

function CheckRow({ check, onFixAction }: { check: PreflightCheck; onFixAction: (action: PreflightFixAction) => void }) {
  const color = STATUS_COLORS[check.status] ?? '#e8e8ea'
  return (
    <div
      data-testid={`preflight-check-${check.id}`}
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: '0.75rem',
        padding: '0.6rem 0',
        borderBottom: '1px solid rgba(255,255,255,0.06)',
      }}
    >
      <span
        aria-label={`Status: ${STATUS_LABELS[check.status] ?? check.status}`}
        style={{
          minWidth: '3rem',
          fontSize: '0.75rem',
          fontWeight: 600,
          color,
          paddingTop: '0.1rem',
        }}
      >
        {STATUS_LABELS[check.status] ?? check.status.toUpperCase()}
      </span>
      <div style={{ flex: 1 }}>
        <div style={{ fontWeight: 500, fontSize: '0.875rem' }}>{check.name}</div>
        <div style={{ fontSize: '0.8rem', color: '#a1a1aa', marginTop: '0.15rem' }}>{check.message}</div>
        {check.fix_action && check.status !== 'pass' && (
          <button
            onClick={() => onFixAction(check.fix_action!)}
            data-testid={`preflight-fix-${check.id}`}
            style={{
              marginTop: '0.4rem',
              padding: '0.25rem 0.6rem',
              borderRadius: '4px',
              border: '1px solid rgba(255,255,255,0.15)',
              background: 'rgba(255,255,255,0.06)',
              color: '#93c5fd',
              fontSize: '0.8rem',
              cursor: 'pointer',
            }}
          >
            {check.fix_action.label} →
          </button>
        )}
      </div>
    </div>
  )
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.75rem', borderBottom: '1px solid rgba(255,255,255,0.08)', paddingBottom: '0.4rem' }}>
      {children}
    </h2>
  )
}

export default function Support() {
  const navigate = useNavigate()
  const [crashState, setCrashState] = useState<CrashBundleState>('idle')
  const [bundlePath, setBundlePath] = useState<string | null>(null)
  const [bundleNotice, setBundleNotice] = useState<string | null>(null)
  const [crashError, setCrashError] = useState<ApiError | null>(null)

  const [betaStep, setBetaStep] = useState<BetaReportStep>('idle')
  const [includeSessionMeta, setIncludeSessionMeta] = useState(false)
  const [betaBundlePath, setBetaBundlePath] = useState<string | null>(null)
  const [betaManifest, setBetaManifest] = useState<string[] | null>(null)
  const [betaError, setBetaError] = useState<ApiError | null>(null)
  const [betaFolderError, setBetaFolderError] = useState<string | null>(null)

  const [selfTestState, setSelfTestState] = useState<SelfTestState>('idle')
  const [selfTestResult, setSelfTestResult] = useState<PreflightResponse | null>(null)
  const [selfTestError, setSelfTestError] = useState<ApiError | null>(null)

  // Maps a wizard-step fix action to its standalone post-setup route. `wizard-step`
  // hrefs (e.g. "choose") name a step inside the first-run wizard, which isn't mounted
  // here — so translate the known steps to the equivalent route (issue #378).
  const WIZARD_STEP_ROUTES: Record<string, string> = { choose: '/model-manager' }

  function handleFixAction(action: PreflightFixAction) {
    const { kind, href } = action
    if (kind === 'open-url' || href.startsWith('http://') || href.startsWith('https://')) {
      void openExternal(href)
    } else if (kind === 'wizard-step') {
      const route = WIZARD_STEP_ROUTES[href]
      if (route) navigate(route)
    } else {
      navigate(href)
    }
  }

  async function handleRunSelfTest() {
    setSelfTestState('running')
    setSelfTestError(null)
    setSelfTestResult(null)
    const r = await api.preflight()
    if (r.ok) {
      setSelfTestResult(r.data)
      setSelfTestState('done')
    } else {
      setSelfTestError(r.error)
      setSelfTestState('error')
    }
  }

  async function handleCreateCrashBundle() {
    setCrashState('creating')
    setCrashError(null)
    setBundlePath(null)
    setBundleNotice(null)
    const r = await api.createCrashBundle()
    if (r.ok) {
      setBundlePath(r.data.bundle_path)
      setBundleNotice(r.data.notice)
      setCrashState('done')
    } else {
      setCrashError(r.error)
      setCrashState('error')
    }
  }

  async function handleCreateBetaReport() {
    setBetaStep('creating')
    setBetaError(null)
    setBetaBundlePath(null)
    setBetaManifest(null)
    setBetaFolderError(null)
    const r = await api.createBetaReport(includeSessionMeta)
    if (r.ok) {
      setBetaBundlePath(r.data.bundle_path)
      setBetaManifest(r.data.manifest)
      setBetaStep('done')
      const parentDir = r.data.bundle_path.replace(/[\\/][^\\/]+$/, '')
      try {
        await openFolderInShell(parentDir)
      } catch {
        // Tauri not available or path rejected — show the path so the user can
        // navigate there manually (non-fatal).
        setBetaFolderError(parentDir)
      }
    } else {
      setBetaError(r.error)
      setBetaStep('error')
    }
  }

  const previewManifest = [
    ...DEFAULT_MANIFEST.slice(0, -1),
    ...(includeSessionMeta
      ? [
          'session_metadata.json — last session: scenario ID, state, turn count, timestamps (no transcript content)',
        ]
      : []),
    'crash-bundle.zip — most recent crash bundle, if one exists (already redacted)',
    DEFAULT_MANIFEST[DEFAULT_MANIFEST.length - 1],
  ]

  return (
    <div style={{ maxWidth: '640px' }}>
      <h1 style={{ marginBottom: '0.5rem' }}>Support</h1>
      <p style={{ fontSize: '0.875rem', color: '#a1a1aa', marginBottom: '2rem' }}>
        Get help, report a bug, or request a feature. All data stays local — nothing is uploaded
        automatically.
      </p>

      {/* ── Self-test ─────────────────────────────────────────────────────── */}
      <section style={{ marginBottom: '2rem' }}>
        <SectionHeading>Self-test</SectionHeading>
        <p style={{ fontSize: '0.875rem', color: '#a1a1aa', marginBottom: '0.75rem' }}>
          Run a quick health check to diagnose common problems. Results show the status of each
          system component with a fix action for anything that needs attention.
        </p>

        <button
          onClick={handleRunSelfTest}
          disabled={selfTestState === 'running'}
          aria-label="Run self-test"
          data-testid="run-self-test-button"
          style={{
            padding: '0.4rem 0.9rem',
            borderRadius: '6px',
            border: '1px solid rgba(255,255,255,0.15)',
            background: 'rgba(255,255,255,0.05)',
            color: selfTestState === 'running' ? '#71717a' : '#e8e8ea',
            fontSize: '0.875rem',
            cursor: selfTestState === 'running' ? 'wait' : 'pointer',
          }}
        >
          {selfTestState === 'running' ? 'Running…' : 'Run self-test'}
        </button>

        {selfTestState === 'done' && selfTestResult && (
          <div
            data-testid="preflight-results"
            style={{ marginTop: '1rem' }}
            aria-label="Self-test results"
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                marginBottom: '0.75rem',
              }}
            >
              <span
                style={{
                  fontSize: '0.8rem',
                  fontWeight: 600,
                  color: STATUS_COLORS[selfTestResult.overall] ?? '#e8e8ea',
                }}
              >
                Overall: {selfTestResult.overall.toUpperCase()}
              </span>
              <span style={{ fontSize: '0.75rem', color: '#71717a' }}>
                — {new Date(selfTestResult.ran_at).toLocaleTimeString()}
              </span>
            </div>
            {selfTestResult.checks.map((check) => (
              <CheckRow key={check.id} check={check} onFixAction={handleFixAction} />
            ))}
          </div>
        )}

        {selfTestState === 'error' && selfTestError && (
          <div data-testid="self-test-error" style={{ marginTop: '0.5rem' }}>
            <ApiErrorView
              error={selfTestError}
              onRetry={handleRunSelfTest}
              context="Support-SelfTest"
            />
          </div>
        )}
      </section>

      {/* ── Report a problem (beta one-click) ─────────────────────────────── */}
      <section style={{ marginBottom: '2rem' }}>
        <SectionHeading>Report a problem</SectionHeading>
        <p style={{ fontSize: '0.875rem', color: '#a1a1aa', marginBottom: '0.75rem' }}>
          Assemble a diagnostics bundle, review its contents, and open a pre-filled GitHub
          issue — all in under a minute. Nothing leaves this device until you explicitly send it.
        </p>
        <p style={{ fontSize: '0.8rem', color: '#a1a1aa', marginBottom: '0.75rem' }}>
          New to the beta? Read the{' '}
          <a
            href={BETA_GUIDE_URL}
            target="_blank"
            rel="noopener noreferrer"
            data-testid="beta-guide-link"
            style={{ color: '#a5b4fc' }}
          >
            beta testing guide →
          </a>{' '}
          for how to join, what to report, and what a good report looks like.
        </p>

        {betaStep === 'idle' && (
          <button
            onClick={() => setBetaStep('consent')}
            data-testid="report-problem-button"
            style={{
              padding: '0.45rem 1rem',
              borderRadius: '6px',
              border: '1px solid rgba(99,102,241,0.4)',
              background: 'rgba(99,102,241,0.12)',
              color: '#a5b4fc',
              fontSize: '0.875rem',
              cursor: 'pointer',
            }}
          >
            Report a problem
          </button>
        )}

        {(betaStep === 'consent') && (
          <div
            role="region"
            aria-label="beta report consent"
            data-testid="beta-report-consent"
            style={{
              background: 'rgba(255,255,255,0.03)',
              border: '1px solid rgba(255,255,255,0.10)',
              borderRadius: '8px',
              padding: '1rem 1.1rem',
            }}
          >
            <p style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.5rem', color: '#e8e8ea' }}>
              Bundle contents
            </p>
            <p style={{ fontSize: '0.8rem', color: '#a1a1aa', marginBottom: '0.6rem' }}>
              The following files will be saved to your crash-bundles folder. Review this list
              before continuing — nothing is written until you click "Create bundle".
            </p>
            <ul
              data-testid="beta-report-manifest-preview"
              style={{ listStyle: 'disc', paddingLeft: '1.2rem', margin: '0 0 0.85rem', fontSize: '0.8rem', color: '#a1a1aa', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}
            >
              {previewManifest.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>

            <label
              style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem', fontSize: '0.8rem', color: '#a1a1aa', cursor: 'pointer', marginBottom: '0.85rem' }}
            >
              <input
                type="checkbox"
                data-testid="include-session-metadata-checkbox"
                checked={includeSessionMeta}
                onChange={(e) => setIncludeSessionMeta(e.target.checked)}
                style={{ marginTop: '2px', flexShrink: 0 }}
              />
              <span>
                Include last session metadata (opt-in) — adds scenario ID, session state,
                turn count, and timestamps. <strong>Never includes transcript content or
                player input.</strong>
              </span>
            </label>

            <div
              role="note"
              aria-label="beta report privacy note"
              style={{
                background: 'rgba(251,191,36,0.08)',
                border: '1px solid rgba(251,191,36,0.2)',
                borderRadius: '6px',
                padding: '0.55rem 0.8rem',
                marginBottom: '0.85rem',
                fontSize: '0.8rem',
                color: '#fde68a',
              }}
            >
              No conversation transcripts, prompts, or audio are ever included. Filesystem paths
              have the username replaced with ~. Nothing is transmitted — you must attach the
              bundle manually.
            </div>

            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              <button
                onClick={() => void handleCreateBetaReport()}
                data-testid="create-beta-report-button"
                style={{
                  padding: '0.4rem 0.9rem',
                  borderRadius: '6px',
                  border: '1px solid rgba(99,102,241,0.4)',
                  background: 'rgba(99,102,241,0.15)',
                  color: '#a5b4fc',
                  fontSize: '0.875rem',
                  cursor: 'pointer',
                }}
              >
                Create bundle
              </button>
              <button
                onClick={() => { setBetaStep('idle'); setIncludeSessionMeta(false) }}
                data-testid="cancel-beta-report-button"
                style={{
                  padding: '0.4rem 0.9rem',
                  borderRadius: '6px',
                  border: '1px solid rgba(255,255,255,0.1)',
                  background: 'transparent',
                  color: '#71717a',
                  fontSize: '0.875rem',
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {betaStep === 'creating' && (
          <p style={{ fontSize: '0.875rem', color: '#a1a1aa' }}>Creating bundle…</p>
        )}

        {betaStep === 'done' && betaBundlePath && (
          <div data-testid="beta-report-success" style={{ marginTop: '0.5rem' }}>
            <p style={{ fontSize: '0.85rem', color: '#86efac', marginBottom: '0.5rem' }}>
              Bundle created. Review its contents before attaching to an issue.
            </p>
            <code
              data-testid="beta-report-path"
              style={{
                display: 'block',
                padding: '0.4rem 0.6rem',
                background: 'rgba(255,255,255,0.05)',
                borderRadius: '4px',
                fontSize: '0.8rem',
                wordBreak: 'break-all',
                marginBottom: '0.5rem',
              }}
            >
              {betaBundlePath}
            </code>
            {betaFolderError && (
              <p style={{ fontSize: '0.8rem', color: '#a1a1aa', marginBottom: '0.5rem' }}>
                Navigate to this folder in your file manager to find the bundle.
              </p>
            )}
            {betaManifest && (
              <ul
                data-testid="beta-report-manifest"
                style={{ listStyle: 'disc', paddingLeft: '1.2rem', margin: '0 0 0.75rem', fontSize: '0.8rem', color: '#71717a', display: 'flex', flexDirection: 'column', gap: '0.2rem' }}
              >
                {betaManifest.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            )}
            <a
              href={BETA_REPORT_TEMPLATE_URL}
              target="_blank"
              rel="noopener noreferrer"
              data-testid="open-beta-issue-link"
              style={{
                display: 'inline-block',
                padding: '0.4rem 0.9rem',
                borderRadius: '6px',
                border: '1px solid rgba(99,102,241,0.4)',
                background: 'rgba(99,102,241,0.12)',
                color: '#a5b4fc',
                fontSize: '0.875rem',
                textDecoration: 'none',
                marginRight: '0.5rem',
              }}
            >
              Open GitHub issue →
            </a>
            <button
              onClick={() => { setBetaStep('idle'); setIncludeSessionMeta(false) }}
              style={{
                padding: '0.4rem 0.9rem',
                borderRadius: '6px',
                border: '1px solid rgba(255,255,255,0.1)',
                background: 'transparent',
                color: '#71717a',
                fontSize: '0.875rem',
                cursor: 'pointer',
              }}
            >
              Done
            </button>
          </div>
        )}

        {betaStep === 'error' && betaError && (
          <div data-testid="beta-report-error" style={{ marginTop: '0.5rem' }}>
            <ApiErrorView
              error={betaError}
              onRetry={() => void handleCreateBetaReport()}
              context="Support-BetaReport"
            />
            <button
              onClick={() => setBetaStep('consent')}
              style={{
                marginTop: '0.5rem',
                padding: '0.35rem 0.8rem',
                borderRadius: '6px',
                border: '1px solid rgba(255,255,255,0.1)',
                background: 'transparent',
                color: '#71717a',
                fontSize: '0.8rem',
                cursor: 'pointer',
              }}
            >
              Back
            </button>
          </div>
        )}
      </section>

      {/* ── Report an issue ───────────────────────────────────────────────── */}
      <section style={{ marginBottom: '2rem' }}>
        <SectionHeading>Report an issue</SectionHeading>
        <p style={{ fontSize: '0.875rem', color: '#a1a1aa', marginBottom: '0.75rem' }}>
          Use a template below to open a pre-filled GitHub issue. Choose the one that best matches
          your situation.
        </p>
        <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
          {ISSUE_TEMPLATES.map(({ key, label, template }) => (
            <li key={key}>
              <a
                href={`${TEMPLATE_BASE}${template}`}
                target="_blank"
                rel="noopener noreferrer"
                data-testid={`issue-template-${key}`}
                style={{
                  display: 'inline-block',
                  color: '#93c5fd',
                  fontSize: '0.875rem',
                  textDecoration: 'none',
                }}
              >
                {label} →
              </a>
            </li>
          ))}
        </ul>
        <p style={{ fontSize: '0.8rem', color: '#71717a', marginTop: '0.75rem' }}>
          Not sure which to pick?{' '}
          <a
            href={ISSUES_URL}
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: '#71717a' }}
          >
            Browse all issue templates →
          </a>
        </p>
      </section>

      {/* ── Crash bundle ─────────────────────────────────────────────────── */}
      <section style={{ marginBottom: '2rem' }}>
        <SectionHeading>Crash bundle</SectionHeading>
        <p style={{ fontSize: '0.875rem', color: '#a1a1aa', marginBottom: '0.75rem' }}>
          A crash bundle contains version info, system details, and recent error log lines. No
          conversation content, prompts, or audio is included. The bundle is saved locally — you
          must attach it to a GitHub issue manually after reviewing its contents.
        </p>

        <div
          role="note"
          aria-label="crash bundle privacy note"
          style={{
            background: 'rgba(251,191,36,0.08)',
            border: '1px solid rgba(251,191,36,0.25)',
            borderRadius: '6px',
            padding: '0.65rem 0.9rem',
            marginBottom: '0.85rem',
            fontSize: '0.85rem',
            color: '#fde68a',
          }}
        >
          Review the bundle contents before attaching it to an issue. Open the file in a text
          editor or zip viewer to confirm it contains only system and version information.
        </div>

        <button
          onClick={handleCreateCrashBundle}
          disabled={crashState === 'creating'}
          aria-label="Create crash bundle"
          data-testid="create-crash-bundle-button"
          style={{
            padding: '0.4rem 0.9rem',
            borderRadius: '6px',
            border: '1px solid rgba(255,255,255,0.15)',
            background: 'rgba(255,255,255,0.05)',
            color: crashState === 'creating' ? '#71717a' : '#e8e8ea',
            fontSize: '0.875rem',
            cursor: crashState === 'creating' ? 'wait' : 'pointer',
          }}
        >
          {crashState === 'creating' ? 'Creating…' : 'Create crash bundle'}
        </button>

        {crashState === 'done' && bundlePath && (
          <div style={{ marginTop: '0.85rem' }}>
            <p style={{ fontSize: '0.85rem', color: '#86efac', marginBottom: '0.4rem' }}>
              Crash bundle created.
            </p>
            <code
              data-testid="crash-bundle-path"
              style={{
                display: 'block',
                padding: '0.4rem 0.6rem',
                background: 'rgba(255,255,255,0.05)',
                borderRadius: '4px',
                fontSize: '0.8rem',
                wordBreak: 'break-all',
                marginBottom: '0.4rem',
              }}
            >
              {bundlePath}
            </code>
            {bundleNotice && (
              <p
                data-testid="crash-bundle-notice"
                style={{ fontSize: '0.8rem', color: '#a1a1aa' }}
              >
                {bundleNotice}
              </p>
            )}
          </div>
        )}

        {crashState === 'error' && crashError && (
          <div data-testid="crash-bundle-error" style={{ marginTop: '0.5rem' }}>
            <ApiErrorView
              error={crashError}
              onRetry={handleCreateCrashBundle}
              context="Support-CrashBundle"
            />
          </div>
        )}
      </section>

      {/* ── Local-first reminder ─────────────────────────────────────────── */}
      <section>
        <SectionHeading>Privacy reminder</SectionHeading>
        <p style={{ fontSize: '0.875rem', color: '#a1a1aa' }}>
          Conversation Simulator is local-first. Conversations, transcripts, audio, and model
          outputs stay on this device unless you explicitly export or share them. No support
          requests are submitted automatically — everything here is manual.
        </p>
      </section>
    </div>
  )
}
