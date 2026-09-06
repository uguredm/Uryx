/** HUD + chrome vurgu paleti — yeşil varsayılan, mavi seçilebilir.
 *  Görünüm tek koyu tema (D23); açık/loş picker yok.
 */

import type { AccentTheme } from '@shared/settings';

export const ACCENT_CACHE_KEY = 'uryx.accentTheme';

export const ACCENT_THEME_SWATCHES: Record<AccentTheme, { from: string; to: string }> = {
  green: { from: '#00d4c0', to: '#006a62' },
  blue: { from: '#3ba3ff', to: '#1a5f9e' },
};

/** Geçersiz değerleri yeşile düşürür. */
export function resolveAccentTheme(theme: string | undefined | null): AccentTheme {
  return theme === 'blue' ? 'blue' : 'green';
}

/** Ok tuşları / HUD döngüsü — iki palet. */
export function cycleAccentTheme(theme: AccentTheme): AccentTheme {
  return theme === 'green' ? 'blue' : 'green';
}

/** Önceki oturumun önbelleği — FOUC önlemek için ilk boyadan önce. */
export function peekCachedAccent(): AccentTheme {
  if (typeof localStorage === 'undefined') return 'green';
  try {
    return resolveAccentTheme(localStorage.getItem(ACCENT_CACHE_KEY));
  } catch {
    return 'green';
  }
}

/** `html[data-accent]` uygular ve yerel önbelleğe yazar. */
export function applyAccentTheme(theme: string | undefined | null): AccentTheme {
  const next = resolveAccentTheme(theme);
  if (typeof document !== 'undefined') {
    document.documentElement.dataset.accent = next;
  }
  if (typeof localStorage !== 'undefined') {
    try {
      localStorage.setItem(ACCENT_CACHE_KEY, next);
    } catch {
    }
  }
  return next;
}

/** Canvas / glow için `--hud-glow` RGB üçlüsü. */
export function readHudGlow(): [number, number, number] {
  if (typeof document === 'undefined') return [0, 212, 192];
  const raw = getComputedStyle(document.documentElement).getPropertyValue('--hud-glow');
  const parts = raw.split(',').map((part) => Number(part.trim()));
  if (parts.length === 3 && parts.every((value) => Number.isFinite(value))) {
    return [parts[0], parts[1], parts[2]];
  }
  return [0, 212, 192];
}
