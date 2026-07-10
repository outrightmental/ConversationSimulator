// SPDX-License-Identifier: Apache-2.0
import { createContext, useContext, useState, type ReactNode } from 'react'
import { en } from './locales/en'
import { de } from './locales/de'

export const LOCALE_KEY = 'convsim.locale'
export const SUPPORTED_LOCALES = ['en', 'de'] as const
export type Locale = (typeof SUPPORTED_LOCALES)[number]

export type TranslateFn = (key: string, params?: Record<string, string | number>) => string

interface I18nContextValue {
  locale: string
  setLocale: (locale: string) => void
  t: TranslateFn
}

const LOCALE_CATALOG: Record<string, Record<string, unknown>> = {
  en: en as unknown as Record<string, unknown>,
  de: de as unknown as Record<string, unknown>,
}

function getNestedValue(obj: Record<string, unknown>, path: string): string | undefined {
  const parts = path.split('.')
  let current: unknown = obj
  for (const part of parts) {
    if (typeof current !== 'object' || current === null) return undefined
    current = (current as Record<string, unknown>)[part]
  }
  return typeof current === 'string' ? current : undefined
}

function interpolate(str: string, params?: Record<string, string | number>): string {
  if (!params) return str
  return str.replace(/\{\{(\w+)\}\}/g, (_, k: string) => String(params[k] ?? `{{${k}}}`))
}

function makeTFn(locale: string): TranslateFn {
  const catalog = LOCALE_CATALOG[locale] ?? LOCALE_CATALOG['en']
  const fallback = LOCALE_CATALOG['en']
  return (key, params) => {
    const value = getNestedValue(catalog, key) ?? getNestedValue(fallback, key) ?? key
    return interpolate(value, params)
  }
}

const DEFAULT_T = makeTFn('en')

export const I18nContext = createContext<I18nContextValue>({
  locale: 'en',
  setLocale: () => {},
  t: DEFAULT_T,
})

function detectLocale(): string {
  try {
    const stored = localStorage.getItem(LOCALE_KEY)
    if (stored && (SUPPORTED_LOCALES as readonly string[]).includes(stored)) return stored
    const lang = navigator.language.split('-')[0]
    if ((SUPPORTED_LOCALES as readonly string[]).includes(lang)) return lang
  } catch {
    // SSR / test environment may not have localStorage or navigator
  }
  return 'en'
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState(detectLocale)

  function setLocale(newLocale: string) {
    if (!(SUPPORTED_LOCALES as readonly string[]).includes(newLocale)) return
    setLocaleState(newLocale)
    try {
      localStorage.setItem(LOCALE_KEY, newLocale)
    } catch {
      // ignore storage errors
    }
  }

  const t = makeTFn(locale)

  return (
    <I18nContext.Provider value={{ locale, setLocale, t }}>
      {children}
    </I18nContext.Provider>
  )
}

export function useTranslation() {
  return useContext(I18nContext)
}

export function formatDate(
  date: Date | string,
  locale: string,
  options?: Intl.DateTimeFormatOptions,
): string {
  const d = typeof date === 'string' ? new Date(date) : date
  return new Intl.DateTimeFormat(locale, options).format(d)
}

export function formatNumber(
  n: number,
  locale: string,
  options?: Intl.NumberFormatOptions,
): string {
  return new Intl.NumberFormat(locale, options).format(n)
}
