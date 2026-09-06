import { resolve } from 'node:path';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  esbuild: {
    jsx: 'automatic',
  },
  test: {
    environment: 'node',
    globals: true,
    include: ['tests/**/*.test.ts', 'tests/**/*.test.tsx'],
    environmentMatchGlobs: [['tests/renderer/**', 'jsdom']],
    setupFiles: ['tests/setup.ts'],
    restoreMocks: true,
  },
  resolve: {
    alias: {
      electron: resolve(__dirname, 'tests/mocks/electron.ts'),
      'electron-store': resolve(__dirname, 'tests/mocks/electron-store.ts'),
      '@': resolve(__dirname, 'src'),
      '@shared': resolve(__dirname, '../../packages/shared-types/src'),
    },
  },
});
