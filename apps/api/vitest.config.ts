import { defineConfig } from 'vitest/config';
import path from 'path';

export default defineConfig({
  // better-sqlite3 is a native Node.js addon (.node binary). Vite's SSR
  // transform pipeline cannot handle it, so we declare it external here so
  // Node.js loads it directly at runtime instead of going through Vite.
  ssr: {
    external: ['better-sqlite3'],
  },
  resolve: {
    alias: {
      '@convsim/shared': path.resolve(__dirname, '../../packages/shared/src/index.ts'),
      '@convsim/pack-loader': path.resolve(__dirname, '../../packages/pack-loader/src/index.ts'),
    },
  },
  test: {
    globals: true,
    include: [
      'src/**/*.test.ts',
      '../../packages/shared/src/**/*.test.ts',
    ],
  },
});
