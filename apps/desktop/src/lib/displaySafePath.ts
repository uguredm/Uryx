/** D16: arayüzde ham kullanıcı yolu yok. */

import { translate } from './messages';
import { getUiLanguage } from './uiLocale';

export const MODELS_DIR_UI_HINT = '%LOCALAPPDATA%\\Uryx\\models';

export function displaySafePath(value: string | null | undefined): string {
  if (!value || !value.trim()) return '';
  const raw = value.trim();
  if (raw.includes('%LOCALAPPDATA%') || raw.includes('%APPDATA%')) return raw;
  const normalized = raw.replace(/\//g, '\\');
  if (/resources\\project/i.test(normalized)) return translate(getUiLanguage(), 'path.dataFolder');
  if (/[A-Za-z]:\\Users\\/i.test(normalized) || normalized.toLowerCase().includes('\\users\\')) {
    const base = normalized.split('\\').filter(Boolean).pop() ?? '';
    return base || translate(getUiLanguage(), 'path.dataFolder');
  }
  return raw;
}
