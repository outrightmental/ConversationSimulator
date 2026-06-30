import { defineConfig } from 'vitest/config';
import path from 'path';

export default defineConfig({
  resolve: {
    alias: {
      '@convsim/shared': path.resolve(__dirname, '../../packages/shared/src/index.ts'),
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
