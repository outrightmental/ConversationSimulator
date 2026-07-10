// SPDX-License-Identifier: Apache-2.0
import { Component, type ErrorInfo, type ReactNode } from 'react'

const ISSUES_URL = 'https://github.com/outrightmental/ConversationSimulator/issues/new/choose'
const DOCS_URL = 'https://github.com/outrightmental/ConversationSimulator/wiki'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  render() {
    const { error } = this.state
    if (error) {
      return (
        <div
          role="alert"
          style={{ padding: '2rem', maxWidth: '40rem', margin: '4rem auto' }}
        >
          <h1>Something went wrong</h1>
          <p>An unexpected error occurred in the app.</p>

          <details style={{ marginTop: '1rem' }}>
            <summary style={{ cursor: 'pointer', color: '#71717a', fontSize: '0.875rem' }}>
              Error details
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
              Try again
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
              Go to home
            </button>
          </div>

          <div style={{ marginTop: '1.25rem', display: 'flex', flexWrap: 'wrap', gap: '0.75rem', fontSize: '0.825rem' }}>
            <a href={ISSUES_URL} target="_blank" rel="noreferrer" style={{ color: '#71717a' }}>
              Report this issue
            </a>
            <span style={{ color: '#52525b' }}>·</span>
            <a href={DOCS_URL} target="_blank" rel="noreferrer" style={{ color: '#71717a' }}>
              Documentation
            </a>
            <span style={{ color: '#52525b' }}>·</span>
            <span style={{ color: '#52525b' }}>
              Logs: <code style={{ fontSize: '0.78rem' }}>~/.convsim/logs</code>
            </span>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
