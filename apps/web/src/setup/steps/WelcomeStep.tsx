// SPDX-License-Identifier: Apache-2.0
import { PrimaryButton } from '../primitives'
import type { UseSetupFlowReturn } from '../useSetupFlow'

const SETUP_DOCS_URL = 'https://docs.conversationsimulator.com/start/install/'

export function WelcomeStep({ flow }: { flow: UseSetupFlowReturn }) {
  return (
    <div style={{ maxWidth: '640px', margin: '2rem auto', padding: '0 1rem' }}>
      <h1 ref={flow.stepHeadingRef} tabIndex={-1} style={{ outline: 'none' }}>Welcome to Conversation Simulator</h1>
      <p style={{ fontSize: '1rem', lineHeight: 1.6, color: '#d4d4d8' }}>
        Conversation Simulator is the private, local-first practice tool for conversations that
        matter — interviews, negotiations, language practice, and difficult discussions at your
        own pace.
      </p>

      <div
        role="note"
        aria-label="privacy and offline-play guarantee"
        style={{
          background: 'rgba(99,102,241,0.08)',
          border: '1px solid rgba(99,102,241,0.3)',
          borderRadius: '8px',
          padding: '1rem 1.25rem',
          marginTop: '1.25rem',
        }}
      >
        <p style={{ margin: 0, fontWeight: 600, color: '#a5b4fc' }}>Your data stays on this machine</p>
        <p style={{ margin: '0.5rem 0 0', fontSize: '0.875rem', color: '#c7d2fe' }}>
          Conversations, transcripts, audio recordings, and AI responses are processed locally
          and never leave your computer unless you choose to export or share them. You can play
          without an internet connection once the model is installed.
        </p>
      </div>

      <div style={{ marginTop: '1.5rem' }}>
        <p style={{ fontWeight: 600, color: '#e8e8ea', margin: '0 0 0.75rem' }}>How it works</p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
          <div aria-label="local model explanation" style={{ border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', padding: '0.85rem 1rem' }}>
            <p style={{ margin: 0, fontWeight: 600, fontSize: '0.875rem' }}>A local AI model powers the conversations</p>
            <p style={{ margin: '0.35rem 0 0', fontSize: '0.825rem', color: '#a1a1aa' }}>
              The app uses a small language model that runs entirely on your machine. After a
              one-time download it works without internet — and nothing is ever sent to a server.
            </p>
          </div>
          <div aria-label="packs explanation" style={{ border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', padding: '0.85rem 1rem' }}>
            <p style={{ margin: 0, fontWeight: 600, fontSize: '0.875rem' }}>Packs give you scenarios to practise</p>
            <p style={{ margin: '0.35rem 0 0', fontSize: '0.825rem', color: '#a1a1aa' }}>
              Scenario packs are collections of practice conversations. A starter pack is already
              installed. You can download more from the library or create your own in the Creator
              Workbench.
            </p>
          </div>
          <div aria-label="text-only demo explanation" style={{ border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', padding: '0.85rem 1rem' }}>
            <p style={{ margin: 0, fontWeight: 600, fontSize: '0.875rem' }}>No download? Try the text-only demo</p>
            <p style={{ margin: '0.35rem 0 0', fontSize: '0.825rem', color: '#a1a1aa' }}>
              Want to explore the interface first? Choose <strong>Continue without a model</strong> in
              the next step. NPC responses are scripted, not AI-generated, but you can try every
              screen immediately.
            </p>
          </div>
        </div>
      </div>

      <p style={{ marginTop: '1.25rem', color: '#a1a1aa', fontSize: '0.875rem' }}>
        This one-time setup wizard helps you choose a local AI model and get ready to play. It
        takes about a minute plus download time. You can change your model at any time from{' '}
        <strong>Settings → Runtime</strong>.
      </p>

      <div style={{ marginTop: '1.25rem', display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
        <PrimaryButton onClick={() => flow.setStep('loading')}>Get started</PrimaryButton>
        <a href={SETUP_DOCS_URL} target="_blank" rel="noreferrer" style={{ fontSize: '0.825rem', color: '#71717a' }}>
          Read setup docs
        </a>
      </div>
    </div>
  )
}
