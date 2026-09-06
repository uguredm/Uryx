import { afterEach, describe, expect, it } from 'vitest';

import {
  ACCENT_CACHE_KEY,
  applyAccentTheme,
  cycleAccentTheme,
  peekCachedAccent,
  resolveAccentTheme,
} from '@/lib/theme';

describe('accent theme', () => {
  afterEach(() => {
    document.documentElement.removeAttribute('data-accent');
    localStorage.removeItem(ACCENT_CACHE_KEY);
  });

  it('geçersiz değeri yeşile düşürür', () => {
    expect(resolveAccentTheme(undefined)).toBe('green');
    expect(resolveAccentTheme('neon')).toBe('green');
    expect(resolveAccentTheme('blue')).toBe('blue');
  });

  it('uygular, önbelleğe yazar ve okur', () => {
    expect(applyAccentTheme('blue')).toBe('blue');
    expect(document.documentElement.dataset.accent).toBe('blue');
    expect(localStorage.getItem(ACCENT_CACHE_KEY)).toBe('blue');
    expect(peekCachedAccent()).toBe('blue');
  });

  it('bozuk önbellek yeşile döner', () => {
    localStorage.setItem(ACCENT_CACHE_KEY, 'purple');
    expect(peekCachedAccent()).toBe('green');
  });

  it('iki palet arasında döner', () => {
    expect(cycleAccentTheme('green')).toBe('blue');
    expect(cycleAccentTheme('blue')).toBe('green');
  });
});
