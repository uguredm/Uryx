import { resolve } from 'node:path';
import { defineConfig, externalizeDepsPlugin } from 'electron-vite';
import react from '@vitejs/plugin-react';

import { rendererManualChunks } from './electron/renderer-chunks';

export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin()],
    build: {
      lib: { entry: resolve(__dirname, 'electron/main.ts') },
      outDir: 'out/main',
      rollupOptions: { output: { format: 'cjs', entryFileNames: 'index.js' } },
    },
    resolve: {
      alias: { '@shared': resolve(__dirname, '../../packages/shared-types/src') },
    },
  },
  preload: {
    plugins: [externalizeDepsPlugin()],
    build: {
      lib: { entry: resolve(__dirname, 'preload/index.ts') },
      outDir: 'out/preload',
      rollupOptions: { output: { format: 'cjs', entryFileNames: 'index.js' } },
    },
    resolve: {
      alias: { '@shared': resolve(__dirname, '../../packages/shared-types/src') },
    },
  },
  renderer: {
    root: '.',
    plugins: [react()],
    resolve: {
      alias: {
        '@': resolve(__dirname, 'src'),
        '@shared': resolve(__dirname, '../../packages/shared-types/src'),
      },
    },
    build: {
      outDir: 'out/renderer',
      rollupOptions: {
        input: resolve(__dirname, 'index.html'),
        output: { manualChunks: rendererManualChunks },
      },
      chunkSizeWarningLimit: 1200,
    },
    server: { port: 5173, strictPort: true },
  },
});
