/** D16: HUD/Ayarlar ham C:\\Users yolu göstermez. */

import { describe, expect, it } from 'vitest';

import { displaySafePath } from '@/lib/displaySafePath';
import { setUiLanguage } from '@/lib/uiLocale';

describe('displaySafePath', () => {
  it('C:\\Users altını dosya adına indirger', () => {
    expect(displaySafePath('C:\\Users\\Example\\AppData\\Local\\Uryx\\models\\a.gguf')).toBe(
      'a.gguf',
    );
  });

  it('repoRoot / resources\\project göstermez', () => {
    setUiLanguage('en');
    expect(displaySafePath('C:\\proj\\resources\\project')).toBe('Uryx data folder');
    setUiLanguage('tr');
    expect(displaySafePath('C:\\proj\\resources\\project')).toBe('Uryx veri klasörü');
    setUiLanguage('en');
  });

  it('%LOCALAPPDATA% ipucunu olduğu gibi bırakır', () => {
    expect(displaySafePath('%LOCALAPPDATA%\\Uryx\\models')).toBe('%LOCALAPPDATA%\\Uryx\\models');
  });
});
