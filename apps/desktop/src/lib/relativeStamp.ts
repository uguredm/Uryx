/**
 * Zulip `relative_time_string_from_date`: ≤2 dk az önce, saat, takvim dün, <90 gün.
 * date-fns / buddy “Active” / timezone tooltip çalınmadı.
 */

import type { UiLanguage } from '@shared/settings';

import { dateLocale, translate } from '@/lib/messages';
import { getUiLanguage } from '@/lib/uiLocale';

function lang(explicit?: UiLanguage): UiLanguage {
  return explicit ?? getUiLanguage();
}

function startOfLocalDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

export function clockStamp(date: Date, language?: UiLanguage): string {
  return date.toLocaleTimeString(dateLocale(lang(language)), {
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function relativeTimeLabel(then: Date, now: Date, language?: UiLanguage): string {
  const ui = lang(language);
  if (Number.isNaN(then.getTime())) return '--:--';
  const minutes = Math.floor((now.getTime() - then.getTime()) / 60_000);
  if (minutes <= 2) return translate(ui, 'fmt.relative.justNow');
  if (minutes < 60) return translate(ui, 'stamp.minutesAgo', { n: minutes });
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return hours === 1
      ? translate(ui, 'stamp.oneHour')
      : translate(ui, 'stamp.hoursAgo', { n: hours });
  }
  const daysOld = Math.round((startOfLocalDay(now) - startOfLocalDay(then)) / 86_400_000);
  if (daysOld === 1) return translate(ui, 'stamp.yesterday');
  if (daysOld < 90) return translate(ui, 'fmt.relative.days', { n: daysOld });
  return then.toLocaleDateString(dateLocale(ui), {
    day: 'numeric',
    month: 'short',
    year: then.getFullYear() === now.getFullYear() ? undefined : 'numeric',
  });
}

export function stampFromIso(
  iso: string,
  now: Date,
  language?: UiLanguage,
): { label: string; title: string } {
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return { label: '--:--', title: '' };
  return { label: relativeTimeLabel(then, now, language), title: clockStamp(then, language) };
}
