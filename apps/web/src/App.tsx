import { useState } from 'react';
import type { SessionCreateResponse } from '@convsim/shared';
import { ScenarioSetupPage } from './pages/ScenarioSetup';

type Page =
  | { name: 'home' }
  | { name: 'setup'; scenarioId: string }
  | { name: 'conversation'; session: SessionCreateResponse };

export function App() {
  const [page, setPage] = useState<Page>({ name: 'home' });

  if (page.name === 'setup') {
    return (
      <ScenarioSetupPage
        scenarioId={page.scenarioId}
        onSessionCreated={(session) => setPage({ name: 'conversation', session })}
        onBack={() => setPage({ name: 'home' })}
      />
    );
  }

  if (page.name === 'conversation') {
    return (
      <div data-testid="conversation-page">
        <p>Session {page.session.session_id} started.</p>
        <button onClick={() => setPage({ name: 'home' })}>End session</button>
      </div>
    );
  }

  return (
    <div data-testid="home-page">
      <h1>Conversation Simulator</h1>
      <p>Flight Simulator for conversations.</p>
      <button
        onClick={() =>
          setPage({ name: 'setup', scenarioId: 'behavioral_interview' })
        }
      >
        Start a scenario
      </button>
    </div>
  );
}
