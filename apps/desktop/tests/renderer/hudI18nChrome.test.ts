import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const root = join(dirname(fileURLToPath(import.meta.url)), '../..');

const HUD_FILES = [
  'src/components/views/UryxDashboard.tsx',
  'src/components/hud/UryxCoreCanvas.tsx',
  'src/components/common/AccentThemePicker.tsx',
  'src/components/layout/UryxWorkspace.tsx',
];

const FORBIDDEN = [
  'Sohbeti markdown indir',
  'Satırı kopyala',
  'Kutuya alıntıla',
  'Dinlemeyi durdur',
  'Konuşmaya başla',
  'aria-label="Arayüz rengi"',
  'title="En alta in"',
];

describe('HUD kromu i18n', () => {
  it('sabit Türkçe title/aria HUD dosyalarında kalmaz', () => {
    const hits: string[] = [];
    for (const file of HUD_FILES) {
      const source = readFileSync(join(root, file), 'utf8');
      for (const needle of FORBIDDEN) {
        if (source.includes(needle)) hits.push(`${file}: ${needle}`);
      }
    }
    expect(hits).toEqual([]);
  });
});
