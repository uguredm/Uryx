/**
 * Native kaydet diyalogu (LobeChat desktopExportService).
 * Renderer yol seçmez; main `showSaveDialog` + yazma.
 * Goose `show-save-dialog` yalnız yol döner — biz yazmayı da main'de tutarız.
 */

import type { UiLanguage } from '@shared/settings';

import { translate } from '../src/lib/messages';

export const SAVE_TEXT_MAX_CHARS = 1_500_000;

function fallbackName(language: UiLanguage): string {
  return translate(language === 'tr' ? 'tr' : 'en', 'export.file');
}

/** Kayıt adı: yol karakteri yok, `.md` zorunlu. */
export function sanitizeSaveFilename(raw: unknown, language: UiLanguage = 'en'): string {
  const cleaned = String(raw ?? '')
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 80);
  const base = cleaned || fallbackName(language);
  return /\.md$/i.test(base) ? base : `${base}.md`;
}

export function ensureMarkdownPath(filePath: string, language: UiLanguage = 'en'): string {
  const trimmed = String(filePath ?? '').trim();
  if (!trimmed) return `${fallbackName(language)}.md`;
  return /\.md$/i.test(trimmed) ? trimmed : `${trimmed}.md`;
}

export function parseSaveTextPayload(
  raw: unknown,
  language: UiLanguage = 'en',
): { defaultName: string; content: string } {
  if (typeof raw === 'string') {
    return { defaultName: sanitizeSaveFilename(raw, language), content: '' };
  }
  const obj =
    raw && typeof raw === 'object' && !Array.isArray(raw) ? (raw as Record<string, unknown>) : {};
  const content = String(obj.content ?? '');
  if (content.length > SAVE_TEXT_MAX_CHARS) {
    throw new Error(translate(language === 'tr' ? 'tr' : 'en', 'export.tooLong'));
  }
  return {
    defaultName: sanitizeSaveFilename(obj.defaultName ?? obj.name, language),
    content,
  };
}
