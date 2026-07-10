#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
// CI pseudo-locale check: scans migrated source files for hardcoded user-visible strings
// that should have been replaced with t() calls.
//
// A "migrated" file is any file listed in MIGRATED_FILES below. Once a file is added
// to that list it is opt-in to the check and any remaining hardcoded strings fail the build.
//
// Run: node scripts/check-i18n.mjs
// Exit 0 = clean, exit 1 = violations found.

import { readFileSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')

// Files that have been migrated to the i18n framework.
// Add a file here once all its user-visible strings have been replaced with t() calls.
const MIGRATED_FILES = [
  'apps/web/src/components/ErrorBoundary.tsx',
  'apps/web/src/error-copy.ts',
  'apps/web/src/layout/AppLayout.tsx',
  'apps/web/src/screens/Home.tsx',
  'apps/web/src/screens/Settings.tsx',
  'apps/web/src/screens/Debrief.tsx',
]

// Patterns that indicate a hardcoded user-visible string outside of JSX.
// We look for JSX text content and string attributes that are English prose
// (2+ words or single capitalized words that are not identifiers/types).
const VIOLATION_PATTERNS = [
  // JSX text content: ><two or more English words<
  { re: />([A-Z][a-z]+ [a-z].{3,})</g, label: 'JSX text content' },
  // aria-label="..." with English prose
  { re: /aria-label="([A-Z][a-z]+ [a-z].{2,})"/g, label: 'aria-label attribute' },
  // placeholder="..." with English prose
  { re: /placeholder="([A-Z][a-z]+ .{2,})"/g, label: 'placeholder attribute' },
  // title="..." with English prose
  { re: /(?<![a-z])title="([A-Z][a-z]+ .{2,})"/g, label: 'title attribute' },
]

// Patterns to allowlist — matches that are never violations.
const ALLOWLIST_PATTERNS = [
  /\{t\(/,                      // already wrapped in t()
  /\/\//,                       // comment lines
  /import /,                    // import statements
  /console\./,                  // console calls
  /SPDX-License/,               // license headers
  /data-testid=/,               // test ids
  /className=/,                 // class names
  /style=/,                     // style attributes
  /href=/,                      // URLs
  /^\/\//,                      // full-line comment
  /rel=/,                       // link rel
  /target=/,                    // link target
  /type=/,                      // input type
  /role=/,                      // aria role (values are ARIA tokens)
  /data-role=/,                 // custom data attrs
  /\.(ts|tsx|js|jsx|mjs)['"`]/, // file path strings
]

let totalViolations = 0

for (const relPath of MIGRATED_FILES) {
  const absPath = resolve(ROOT, relPath)
  let source
  try {
    source = readFileSync(absPath, 'utf8')
  } catch {
    console.error(`[check-i18n] ERROR: cannot read ${relPath}`)
    totalViolations++
    continue
  }

  const lines = source.split('\n')
  const fileViolations = []

  for (let lineIdx = 0; lineIdx < lines.length; lineIdx++) {
    const line = lines[lineIdx]
    const lineNum = lineIdx + 1

    // Skip lines that are clearly allowlisted
    if (ALLOWLIST_PATTERNS.some((p) => p.test(line))) continue

    for (const { re, label } of VIOLATION_PATTERNS) {
      re.lastIndex = 0
      let match
      while ((match = re.exec(line)) !== null) {
        const text = match[1].trim()
        // Skip short strings (single word, all-caps constants, etc.)
        if (!text.includes(' ') && text === text.toUpperCase()) continue
        if (text.length < 4) continue
        fileViolations.push({ lineNum, label, text })
      }
    }
  }

  if (fileViolations.length > 0) {
    console.error(`\n[check-i18n] FAIL: ${relPath} — ${fileViolations.length} violation(s)`)
    for (const { lineNum, label, text } of fileViolations) {
      console.error(`  Line ${lineNum} [${label}]: "${text}"`)
    }
    totalViolations += fileViolations.length
  }
}

// Layout audit: report German string length expansion vs English for key strings.
// German is ~30-35% longer than English; this audit reports the ratio as a build artifact.
const EN_PATH = resolve(ROOT, 'apps/web/src/i18n/locales/en.ts')
const DE_PATH = resolve(ROOT, 'apps/web/src/i18n/locales/de.ts')

function extractStrings(src) {
  const strings = []
  const re = /:\s*'([^']{10,})'/g
  let m
  while ((m = re.exec(src)) !== null) {
    strings.push(m[1])
  }
  return strings
}

try {
  const enSrc = readFileSync(EN_PATH, 'utf8')
  const deSrc = readFileSync(DE_PATH, 'utf8')
  const enStrings = extractStrings(enSrc)
  const deStrings = extractStrings(deSrc)

  if (enStrings.length > 0 && deStrings.length > 0) {
    const enTotal = enStrings.reduce((s, x) => s + x.length, 0)
    const deTotal = deStrings.reduce((s, x) => s + x.length, 0)
    const ratio = deTotal / enTotal
    const pct = ((ratio - 1) * 100).toFixed(1)
    const sign = ratio >= 1 ? '+' : ''
    console.log(`\n[check-i18n] Layout audit: German catalog is ${sign}${pct}% vs English by character count (${deTotal} vs ${enTotal})`)
    if (ratio < 1.1) {
      console.warn('[check-i18n] WARNING: German strings appear shorter than expected — verify translations are complete')
    }
  }
} catch {
  // Non-fatal: catalog files may not exist in partial runs
}

if (totalViolations === 0) {
  console.log('\n[check-i18n] All migrated files are clean.')
  process.exit(0)
} else {
  console.error(`\n[check-i18n] ${totalViolations} violation(s) found. Replace hardcoded strings with t() calls.`)
  process.exit(1)
}
