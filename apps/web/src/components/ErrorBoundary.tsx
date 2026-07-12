// SPDX-License-Identifier: Apache-2.0
// First component migrated to the i18n framework (issue #312).
// A functional wrapper reads the translation function via useTranslation() and
// passes it down to the class-based error boundary, which must remain a class
// component because React does not support error boundary hooks.
import { Component, type ErrorInfo, type ReactNode } from 'react'
import { useTranslation, type TranslateFn } from '../i18n'

const ISSUES_URL = 'https://github.com/outrightmental/ConversationSimulator/issues/new/choose'
const DOCS_URL = 'https://docs.conversationsimulator.com/start/troubleshooting/'

interface Props {
  children: ReactNode
}

interface InnerProps extends Props {
  t: TranslateFn
}

interface State {
  error: Error | null
}

class ErrorBoundaryInner extends Component<InnerProps, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  render() {
    const { error } = this.state
    const { t } = this.props
    if (error) {
      return (
        <div
          role="alert"
          style={{ padding: '2rem', maxWidth: '40rem', margin: '4rem auto' }}
        >
          <h1>{t('error.heading')}</h1>
          <p>{t('error.subheading')}</p>

          <details style={{ marginTop: '1rem' }}>
            <summary style={{ cursor: 'pointer', color: '#71717a', fontSize: '0.875rem' }}>
              {t('error.details')}
            </summary>
            <pre
              style={{
                whiteSpace: 'pre-wrap',
                marginTop: '0.5rem',
                fontSize: '0.8rem',
                color: '#a1a1aa',
                background: 'rgba(255,255,255,0.04)',
                border: '1px solid rgba(255,255,255,0.08)',
                borderRadius: '4px',
                padding: '0.75rem',
              }}
            >
              {error.message}
            </pre>
          </details>

          <div style={{ marginTop: '1.5rem', display: 'flex', flexWrap: 'wrap', gap: '0.5rem', alignItems: 'center' }}>
            <button
              style={{
                padding: '0.45rem 1rem',
                borderRadius: '4px',
                border: 'none',
                background: 'rgba(99,102,241,0.85)',
                color: '#fff',
                cursor: 'pointer',
                fontSize: '0.875rem',
                fontWeight: 500,
              }}
              onClick={() => this.setState({ error: null })}
            >
              {t('error.tryAgain')}
            </button>
            <button
              style={{
                padding: '0.45rem 1rem',
                borderRadius: '4px',
                border: '1px solid rgba(255,255,255,0.2)',
                background: 'rgba(255,255,255,0.06)',
                color: 'inherit',
                cursor: 'pointer',
                fontSize: '0.875rem',
                fontWeight: 500,
              }}
              onClick={() => {
                this.setState({ error: null })
                window.location.href = '/'
              }}
            >
              {t('error.goHome')}
            </button>
          </div>

          <div style={{ marginTop: '1.25rem', display: 'flex', flexWrap: 'wrap', gap: '0.75rem', fontSize: '0.825rem' }}>
            <a href={ISSUES_URL} target="_blank" rel="noreferrer" style={{ color: '#71717a' }}>
              {t('error.reportIssue')}
            </a>
            <span style={{ color: '#52525b' }}>·</span>
            <a href={DOCS_URL} target="_blank" rel="noreferrer" style={{ color: '#71717a' }}>
              {t('error.documentation')}
            </a>
            <span style={{ color: '#52525b' }}>·</span>
            <span style={{ color: '#52525b' }}>
              {t('error.logsLabel')} <code style={{ fontSize: '0.78rem' }}>~/.convsim/logs</code>
            </span>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

export default function ErrorBoundary({ children }: Props) {
  const { t } = useTranslation()
  return <ErrorBoundaryInner t={t}>{children}</ErrorBoundaryInner>
}
