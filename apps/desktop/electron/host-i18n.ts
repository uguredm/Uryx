/** Electron main — arayüz diline göre host mesajı. Store döngüsü yok. */

import type { UiLanguage } from '@shared/settings';

import { translate, type MessageKey } from '../src/lib/messages';

let language: UiLanguage = 'en';

export function setHostLanguage(next: UiLanguage): void {
  language = next === 'tr' ? 'tr' : 'en';
}

export function hostLang(): UiLanguage {
  return language;
}

export function hostT(key: MessageKey, vars?: Record<string, string | number>): string {
  return translate(language, key, vars);
}

/** Kod-yanı TR/EN — host araç hataları messages.ts’e yığılmasın. */
export function hostText(tr: string, en: string): string {
  return language === 'tr' ? tr : en;
}
