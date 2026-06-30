// SPDX-License-Identifier: Apache-2.0
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
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
