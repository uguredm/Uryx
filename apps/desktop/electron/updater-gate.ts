/** Paketli kurulumda güncelleme başlar. Kanal: önce public, gerekirse gizli+token. */

import type { UiLanguage } from '@shared/settings';

import { translate } from '../src/lib/messages';

export type UpdaterFeed = 'public' | 'private';
export type UpdaterFeedNext = UpdaterFeed | 'give-up';
export type UpdaterErrorKind = 'not-found' | 'auth' | 'network' | 'other';

export function updaterStartDecision(packaged: boolean): 'start' | 'unpackaged' {
  return packaged ? 'start' : 'unpackaged';
}

export function classifyUpdaterError(message: string): UpdaterErrorKind {
  const lower = message.toLowerCase();
  if (
    lower.includes('enet') ||
    lower.includes('timed out') ||
    lower.includes('timeout') ||
    lower.includes('network') ||
    lower.includes('err_timed_out') ||
    lower.includes('err_internet') ||
    lower.includes('err_connection') ||
    lower.includes('err_name_not_resolved')
  ) {
    return 'network';
  }
  if (lower.includes('401') || lower.includes('403') || lower.includes('bad credentials')) {
    return 'auth';
  }
  if (lower.includes('404') || lower.includes('not found') || lower.includes('latest.yml')) {
    return 'not-found';
  }
  return 'other';
}

export function productSafeUpdaterMessage(input: {
  kind: UpdaterErrorKind;
  feed: UpdaterFeed | null;
  language?: UiLanguage;
}): string {
  const language = input.language === 'tr' ? 'tr' : 'en';
  if (input.kind === 'network') {
    return translate(language, 'update.network');
  }
  if (input.kind === 'not-found' || input.kind === 'auth') {
    return translate(language, 'update.none');
  }
  return translate(language, 'update.checkFail');
}

export function nextUpdaterFeed(input: {
  current: UpdaterFeed | null;
  hasToken: boolean;
  error: string | null;
}): UpdaterFeedNext {
  if (input.current === null) return 'public';
  if (!input.error) return 'give-up';
  if (input.current === 'private') return 'give-up';
  const kind = classifyUpdaterError(input.error);
  if (kind === 'network' || kind === 'other') return 'give-up';
  if ((kind === 'not-found' || kind === 'auth') && input.hasToken) return 'private';
  return 'give-up';
}
