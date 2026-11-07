// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from 'react'
import { useTranslation } from '../i18n'
import FamiliarityQuestion from './FamiliarityQuestion'
import {
  hasSeenFamiliarityReask,
  levelForFamiliarity,
  markFamiliarityReaskShown,
} from '../lib/plainLanguage'

/** The scenario whose debrief triggers the re-ask. */
export const TUTORIAL_SCENARIO_ID = 'first_words_tutorial'

/**
 * The post-tutorial re-ask (issue #501 §2).
 *
 * "That question might be asked again after completing the tutorial" — because
 * a player who answered "new to this" before seeing anything now knows what
 * the app actually shows them, and may want more or less of it.
 *
 * Automatic but not blocking, and shown once: a card on the tutorial debrief,
 * among the other things that debrief offers, rather than a modal in front of
 * it. It marks itself seen when it renders, so ignoring it — which is what
 * most players will do, since the debrief's buttons navigate away — counts as
 * an answer of "leave it alone" instead of re-nagging after the next session.
 */
export default function FamiliarityReaskCard({ scenarioId }: { scenarioId?: string | null }) {
  const { t } = useTranslation()
  const [visible, setVisible] = useState(
    () => scenarioId === TUTORIAL_SCENARIO_ID && !hasSeenFamiliarityReask(),
  )
  const [applied, setApplied] = useState<'plain' | 'technical' | null>(null)

  useEffect(() => {
    if (visible) markFamiliarityReaskShown()
  }, [visible])

  if (!visible) return null

  return (
    <section
      data-testid="familiarity-reask"
      aria-label={t('familiarity.reaskQuestion')}
      style={{
        padding: '0.85rem 1rem',
        borderRadius: 8,
        border: '1px solid rgba(99,102,241,0.3)',
        background: 'rgba(99,102,241,0.07)',
      }}
    >
      <FamiliarityQuestion
        heading={t('familiarity.reaskQuestion')}
        compact
        onAnswered={(answer) => setApplied(levelForFamiliarity(answer))}
      />
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.75rem',
          flexWrap: 'wrap',
          marginTop: '0.6rem',
        }}
      >
        <p aria-live="polite" style={{ margin: 0, fontSize: '0.78rem', color: applied ? '#86efac' : '#71717a', flex: 1 }}>
          {applied === 'plain'
            ? t('familiarity.appliedPlain')
            : applied === 'technical'
            ? t('familiarity.appliedTechnical')
            : t('familiarity.reaskHint')}
        </p>
        <button
          onClick={() => setVisible(false)}
          data-testid="familiarity-reask-dismiss"
          style={{
            padding: '0.25rem 0.7rem',
            borderRadius: '4px',
            border: '1px solid rgba(255,255,255,0.15)',
            background: 'transparent',
            color: '#a1a1aa',
            fontSize: '0.78rem',
            cursor: 'pointer',
          }}
        >
          {applied ? t('familiarity.keep') : t('familiarity.skip')}
        </button>
      </div>
    </section>
  )
}
