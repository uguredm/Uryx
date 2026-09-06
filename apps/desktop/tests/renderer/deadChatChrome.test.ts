import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const root = join(dirname(fileURLToPath(import.meta.url)), '../..');

describe('ölü sohbet kromu', () => {
  it('App ChatView ve Sidebar import etmez', () => {
    const app = readFileSync(join(root, 'src/App.tsx'), 'utf8');
    expect(app).not.toMatch(/ChatView/);
    expect(app).not.toMatch(/Sidebar/);
  });

  it('ChatView ve Sidebar dosyaları yok', () => {
    expect(existsSync(join(root, 'src/components/views/ChatView.tsx'))).toBe(false);
    expect(existsSync(join(root, 'src/components/layout/Sidebar.tsx'))).toBe(false);
  });
});
