/** Store/API dışı çeviri — React hook yok. */

import { translate, type MessageKey } from '@/lib/messages';
import { getUiLanguage } from '@/lib/uiLocale';

export function tNow(
  key: MessageKey,
  vars?: Record<string, string | number>,
): string {
  return translate(getUiLanguage(), key, vars);
}
