// SPDX-License-Identifier: Apache-2.0
import { useState } from 'react'
import { api } from '../api/client'
import type { ApiError } from '../api/errors'
import { ApiErrorView } from '../components/ApiErrorView'

const ISSUES_URL = 'https://github.com/outrightmental/ConversationSimulator/issues/new/choose'
const TEMPLATE_BASE = 'https://github.com/outrightmental/ConversationSimulator/issues/new?template='

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

type CrashBundleState = 'idle' | 'creating' | 'done' | 'error'

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.75rem', borderBottom: '1px solid rgba(255,255,255,0.08)', paddingBottom: '0.4rem' }}>
      {children}
    </h2>
  )
}

export default function Support() {
  const [crashState, setCrashState] = useState<CrashBundleState>('idle')
  const [bundlePath, setBundlePath] = useState<string | null>(null)
  const [bundleNotice, setBundleNotice] = useState<string | null>(null)
  const [crashError, setCrashError] = useState<ApiError | null>(null)

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

  return (
    <div style={{ maxWidth: '640px' }}>
      <h1 style={{ marginBottom: '0.5rem' }}>Support</h1>
      <p style={{ fontSize: '0.875rem', color: '#a1a1aa', marginBottom: '2rem' }}>
        Get help, report a bug, or request a feature. All data stays local — nothing is uploaded
        automatically.
      </p>

      {/* Report an issue */}
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

      {/* Crash bundle */}
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

      {/* Local-first reminder */}
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
