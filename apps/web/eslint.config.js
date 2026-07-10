// SPDX-License-Identifier: Apache-2.0
import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      'no-restricted-syntax': [
        'error',
        {
          selector: 'CallExpression[callee.name="fetch"]',
          message:
            'Direct fetch() calls are not allowed outside api/client.ts. Use the typed API client instead.',
        },
      ],
    },
  },
  {
    // api/client.ts is the one permitted fetch site.
    // CoreStartup.tsx does a Tauri-only health ping that predates the typed
    // client and is structurally separate (AbortSignal timeout, no JSON parsing).
    files: ['**/api/client.ts', '**/screens/CoreStartup.tsx'],
    rules: {
      'no-restricted-syntax': 'off',
    },
  },
)
