// SPDX-License-Identifier: Apache-2.0
import { resolve } from 'path'
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // @convsim/scenario-schema ships source-only (no dist build step).
      // Point Vite/Vitest directly at the TypeScript source so tests work
      // without requiring a build pass first.
      '@convsim/scenario-schema': resolve(
        __dirname,
        '../../packages/scenario-schema/src/index.ts',
      ),
    },
  },
  server: {
    host: '127.0.0.1',
    port: 7354,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:7355',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://127.0.0.1:7355',
        ws: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/setupTests.ts'],
    globals: true,
  },
})
