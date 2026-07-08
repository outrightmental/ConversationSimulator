// SPDX-License-Identifier: Apache-2.0
// Resolve workspace packages to their TypeScript source so tests run without
// a prior build step (matching the pattern used by pack-loader's own tests,
// which import from '../src/...' directly).
import { defineConfig } from 'vitest/config';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const dir = fileURLToPath(new URL('.', import.meta.url));

export default defineConfig({
  resolve: {
    alias: {
      '@convsim/pack-loader': resolve(dir, '../pack-loader/src/index.ts'),
    },
  },
});
