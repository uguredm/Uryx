import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

import { rendererManualChunks } from '../electron/renderer-chunks';

describe('rendererManualChunks', () => {
  it('react, highlight.js ve markdown paketlerini ayırır', () => {
    expect(rendererManualChunks('/proj/node_modules/react/index.js')).toBe('react');
    expect(rendererManualChunks('C:\\proj\\node_modules\\react-dom\\cjs\\react-dom.production.js')).toBe(
      'react',
    );
    expect(rendererManualChunks('/proj/node_modules/highlight.js/lib/core.js')).toBe('highlight');
    expect(rendererManualChunks('/proj/node_modules/react-markdown/index.js')).toBe('markdown');
  });

  it('uygulama kaynaklarını bölmez', () => {
    expect(rendererManualChunks('/apps/desktop/src/App.tsx')).toBeUndefined();
    expect(rendererManualChunks('/apps/desktop/electron/main.ts')).toBeUndefined();
  });
});

describe('electron.vite.config.ts', () => {
  const src = readFileSync(resolve(__dirname, '../electron.vite.config.ts'), 'utf8');

  it('manualChunks yalnız renderer output’ta vardır', () => {
    expect(src).toMatch(/manualChunks:\s*rendererManualChunks/);
    expect(src.match(/manualChunks/g)?.length).toBe(1);
  });
});
