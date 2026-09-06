/** Renderer dilinin API/store dışı okuması — settingsStore döngüsü yok. */

import type { UiLanguage } from '@shared/settings';

let language: UiLanguage = 'en';

export function setUiLanguage(next: UiLanguage): void {
  language = next === 'tr' ? 'tr' : 'en';
}

export function getUiLanguage(): UiLanguage {
  return language;
}
