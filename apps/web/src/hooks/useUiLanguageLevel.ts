// SPDX-License-Identifier: Apache-2.0
import { useCallback, useEffect, useState } from 'react'
import {
  UI_LANGUAGE_CHANGE_EVENT,
  UI_LANGUAGE_KEYS,
  readUiLanguageLevel,
  writeUiLanguageLevel,
  type UiLanguageLevel,
} from '../lib/plainLanguage'

/**
 * The player's plain-vs-technical language level, live (issue #501 §2).
 *
 * Subscribes to both the in-document change event (a switch flipped in
 * Settings while a Conversation is mounted behind it) and `storage` (the same
 * profile open in a second window), so no screen is left showing the old
 * vocabulary until it happens to re-mount.
 */
export function useUiLanguageLevel(): {
  level: UiLanguageLevel
  isPlain: boolean
  setLevel: (level: UiLanguageLevel) => void
} {
  const [level, setLevelState] = useState<UiLanguageLevel>(readUiLanguageLevel)

  useEffect(() => {
    function sync() {
      setLevelState(readUiLanguageLevel())
    }
    function onStorage(e: StorageEvent) {
      if (e.key === null || e.key === UI_LANGUAGE_KEYS.level) sync()
    }
    window.addEventListener(UI_LANGUAGE_CHANGE_EVENT, sync)
    window.addEventListener('storage', onStorage)
    return () => {
      window.removeEventListener(UI_LANGUAGE_CHANGE_EVENT, sync)
      window.removeEventListener('storage', onStorage)
    }
  }, [])

  const setLevel = useCallback((next: UiLanguageLevel) => {
    writeUiLanguageLevel(next)
    setLevelState(next)
  }, [])

  return { level, isPlain: level === 'plain', setLevel }
}
