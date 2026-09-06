/** Arayüz metinleri — D25 varsayılan İngilizce; Türkçe Ayarlar’dan. */

import { useCallback } from 'react';
import type { UiLanguage } from '@shared/settings';

import { useSettingsStore } from '@/stores/settingsStore';
import { dateLocale, translate, type MessageKey } from '@/lib/messages';

export {
  composePhaseLabel,
  dateLocale,
  MESSAGE_TABLES,
  translate,
  type MessageKey,
} from '@/lib/messages';

export function useI18n(): {
  language: UiLanguage;
  locale: string;
  t: (key: MessageKey, vars?: Record<string, string | number>) => string;
} {
  const language = useSettingsStore((state) => state.settings.language) ?? 'en';
  const t = useCallback(
    (key: MessageKey, vars?: Record<string, string | number>) => translate(language, key, vars),
    [language],
  );
  return { language, locale: dateLocale(language), t };
}
