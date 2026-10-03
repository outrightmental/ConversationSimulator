// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { I18nProvider } from '../i18n'
import WordingPanel from '../components/WordingPanel'
import FamiliarityQuestion from '../components/FamiliarityQuestion'
import FamiliarityReaskCard from '../components/FamiliarityReaskCard'
import { UI_LANGUAGE_KEYS, readLlmFamiliarity, readUiLanguageLevel } from '../lib/plainLanguage'

function renderIn(ui: React.ReactElement) {
  return render(<I18nProvider>{ui}</I18nProvider>)
}

beforeEach(() => {
  localStorage.clear()
})

/**
 * Issue #501 §2: "customizable buffers between user and technical language,
 * perhaps chosen by an initial LLM familiarity question. That question might
 * be asked again after completing the tutorial."
 */
describe('WordingPanel', () => {
  it('shows plain wording as the active level by default', () => {
    renderIn(<WordingPanel />)
    expect(screen.getByTestId('wording-plain')).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByTestId('wording-technical')).toHaveAttribute('aria-checked', 'false')
  })

  it('switching to technical persists and takes effect', () => {
    renderIn(<WordingPanel />)
    fireEvent.click(screen.getByTestId('wording-technical'))
    expect(readUiLanguageLevel()).toBe('technical')
    expect(screen.getByTestId('wording-technical')).toHaveAttribute('aria-checked', 'true')
  })

  it('reflects a level chosen elsewhere', () => {
    localStorage.setItem(UI_LANGUAGE_KEYS.level, 'technical')
    renderIn(<WordingPanel />)
    expect(screen.getByTestId('wording-technical')).toHaveAttribute('aria-checked', 'true')
  })
})

describe('FamiliarityQuestion', () => {
  it('asks about the player, not about the setting', () => {
    // Nobody arriving for the first time knows whether they want "technical
    // wording"; everyone knows whether they work with language models.
    renderIn(<FamiliarityQuestion heading="How familiar are you with AI language models?" />)
    expect(
      screen.getByText('How familiar are you with AI language models?'),
    ).toBeInTheDocument()
    expect(screen.getByTestId('familiarity-new')).toHaveTextContent('New to this')
    expect(screen.getByTestId('familiarity-expert')).toHaveTextContent('I work with them')
  })

  it('"new to this" keeps plain wording', () => {
    renderIn(<FamiliarityQuestion heading="q" />)
    fireEvent.click(screen.getByTestId('familiarity-new'))
    expect(readLlmFamiliarity()).toBe('new')
    expect(readUiLanguageLevel()).toBe('plain')
  })

  it('"I work with them" turns the identifiers on', () => {
    renderIn(<FamiliarityQuestion heading="q" />)
    fireEvent.click(screen.getByTestId('familiarity-expert'))
    expect(readUiLanguageLevel()).toBe('technical')
  })

  it('leaves plain wording in place when nobody answers', () => {
    renderIn(<FamiliarityQuestion heading="q" />)
    expect(readLlmFamiliarity()).toBeNull()
    expect(readUiLanguageLevel()).toBe('plain')
  })

  it('preselects a previous answer', () => {
    renderIn(<FamiliarityQuestion heading="q" />)
    fireEvent.click(screen.getByTestId('familiarity-some'))
    // Re-render as the post-tutorial re-ask would.
    renderIn(<FamiliarityQuestion heading="q again" />)
    const options = screen.getAllByTestId('familiarity-some')
    expect(options[options.length - 1]).toHaveAttribute('aria-checked', 'true')
  })
})

describe('FamiliarityReaskCard', () => {
  it('appears on the tutorial debrief', () => {
    renderIn(<FamiliarityReaskCard scenarioId="first_words_tutorial" />)
    expect(screen.getByTestId('familiarity-reask')).toBeInTheDocument()
  })

  it('does not appear on any other debrief', () => {
    const { container } = renderIn(<FamiliarityReaskCard scenarioId="behavioral_interview" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('does not appear when the scenario is unknown', () => {
    const { container } = renderIn(<FamiliarityReaskCard scenarioId={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('appears once — ignoring it counts as an answer', () => {
    // The debrief's action buttons navigate away, so most players will never
    // click this. Re-nagging after every later session is the failure mode.
    const first = renderIn(<FamiliarityReaskCard scenarioId="first_words_tutorial" />)
    expect(screen.getByTestId('familiarity-reask')).toBeInTheDocument()
    first.unmount()

    const second = renderIn(<FamiliarityReaskCard scenarioId="first_words_tutorial" />)
    expect(second.container).toBeEmptyDOMElement()
  })

  it('applies an answer and confirms it in place', () => {
    renderIn(<FamiliarityReaskCard scenarioId="first_words_tutorial" />)
    fireEvent.click(screen.getByTestId('familiarity-expert'))
    expect(readUiLanguageLevel()).toBe('technical')
    expect(screen.getByText(/technical detail is on/i)).toBeInTheDocument()
  })

  it('can be dismissed without answering', () => {
    renderIn(<FamiliarityReaskCard scenarioId="first_words_tutorial" />)
    fireEvent.click(screen.getByTestId('familiarity-reask-dismiss'))
    expect(screen.queryByTestId('familiarity-reask')).not.toBeInTheDocument()
    expect(readUiLanguageLevel()).toBe('plain')
  })
})
