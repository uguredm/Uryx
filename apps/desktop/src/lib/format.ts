/** Türkçe / İngilizce biçimlendirme yardımcıları. */

import type { UiLanguage } from '@shared/settings';

import { dateLocale, translate } from '@/lib/messages';
import { getUiLanguage } from '@/lib/uiLocale';

function lang(explicit?: UiLanguage): UiLanguage {
  return explicit ?? getUiLanguage();
}

function decimal(value: string, language: UiLanguage): string {
  return language === 'tr' ? value.replace('.', ',') : value;
}

/** Ondalık ayırıcıyı arayüz diline göre yazar. */
export function formatDecimal(value: string | number, language?: UiLanguage): string {
  return decimal(String(value), lang(language));
}

/** ISO tarihi "12 Oca 14:30" / "Jan 12, 2:30 PM" biçimine çevirir. */
export function formatDateTime(
  iso: string | null | undefined,
  language?: UiLanguage,
): string {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '—';
  return new Intl.DateTimeFormat(dateLocale(lang(language)), {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

/** ISO tarihinden saat döndürür. */
export function formatTime(iso: string | null | undefined, language?: UiLanguage): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat(dateLocale(lang(language)), {
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

/** "3 dakika önce" gibi göreli zaman üretir. */
export function formatRelative(iso: string | null | undefined, language: UiLanguage = 'en'): string {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '—';

  const seconds = Math.round((Date.now() - date.getTime()) / 1000);
  if (seconds < 60) return translate(language, 'fmt.relative.justNow');
  if (seconds < 3600) {
    return translate(language, 'fmt.relative.minutes', { n: Math.floor(seconds / 60) });
  }
  if (seconds < 86_400) {
    return translate(language, 'fmt.relative.hours', { n: Math.floor(seconds / 3600) });
  }
  if (seconds < 604_800) {
    return translate(language, 'fmt.relative.days', { n: Math.floor(seconds / 86_400) });
  }
  return formatDateTime(iso, language);
}

/** Bayt sayısını okunabilir hâle getirir. */
export function formatBytes(bytes: number, language?: UiLanguage): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** index;
  const raw = value.toFixed(index === 0 ? 0 : 1);
  return `${decimal(raw, lang(language))} ${units[index]}`;
}

/** Milisaniyeyi okunabilir süreye çevirir. */
export function formatDuration(ms: number, language?: UiLanguage): string {
  const ui = lang(language);
  if (!Number.isFinite(ms) || ms < 0) return '—';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  if (ms < 60_000) {
    return `${decimal((ms / 1000).toFixed(1), ui)} ${translate(ui, 'fmt.sec')}`;
  }
  return translate(ui, 'fmt.minSec', {
    m: Math.floor(ms / 60_000),
    s: Math.round((ms % 60_000) / 1000),
  });
}

/** Yüzdeyi tek ondalıkla biçimler. */
export function formatPercent(value: number, language?: UiLanguage): string {
  const raw = (Math.round(value * 10) / 10).toString();
  return `${decimal(raw, lang(language))}%`;
}

/** MB değerini GB'ye çevirir. */
export function mbToGb(mb: number, language?: UiLanguage): string {
  return `${decimal((mb / 1024).toFixed(1), lang(language))} GB`;
}

/** Servis durumunu arayüz diline çevirir. */
export function serviceStateLabel(state: string, language: UiLanguage = 'en'): string {
  if (
    state === 'up' ||
    state === 'down' ||
    state === 'starting' ||
    state === 'degraded' ||
    state === 'unknown'
  ) {
    return translate(language, `fmt.service.${state}`);
  }
  return state;
}

/** Hafıza kategorisini arayüz diline çevirir. */
export function memoryCategoryLabel(category: string, language: UiLanguage = 'en'): string {
  if (
    category === 'preference' ||
    category === 'system_info' ||
    category === 'project' ||
    category === 'folder' ||
    category === 'application' ||
    category === 'contact' ||
    category === 'fact' ||
    category === 'other'
  ) {
    return translate(language, `fmt.memory.${category}`);
  }
  return category;
}

/** Belge durumunu arayüz diline çevirir. */
export function documentStatusLabel(status: string, language: UiLanguage = 'en'): string {
  if (
    status === 'pending' ||
    status === 'parsing' ||
    status === 'embedding' ||
    status === 'indexed' ||
    status === 'failed'
  ) {
    return translate(language, `fmt.doc.${status}`);
  }
  return status;
}

/** Risk seviyesini arayüz diline çevirir. */
export function riskLabel(risk: string, language: UiLanguage = 'en'): string {
  if (risk === 'low' || risk === 'medium' || risk === 'high') {
    return translate(language, `risk.${risk}`);
  }
  return risk;
}

/** Metni belirtilen uzunlukta keser. */
export function truncate(text: string, length = 120): string {
  const clean = text.trim();
  return clean.length <= length ? clean : `${clean.slice(0, length)}…`;
}
