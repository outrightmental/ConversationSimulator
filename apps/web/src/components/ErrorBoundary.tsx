// SPDX-License-Identifier: Apache-2.0
import { Component, type ErrorInfo, type ReactNode } from 'react'

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
          <p>An unexpected error occurred. Try refreshing the page.</p>
          <details style={{ marginTop: '1rem' }}>
            <summary>Error details</summary>
            <pre style={{ whiteSpace: 'pre-wrap', marginTop: '0.5rem' }}>
              {error.message}
            </pre>
          </details>
          <button
            style={{ marginTop: '1.5rem', padding: '0.5rem 1.5rem' }}
            onClick={() => this.setState({ error: null })}
          >
            Try again
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
