import { afterEach, describe, expect, it } from 'vitest';

import {
  COMPOSER_DRAFT_KEY,
  COMPOSER_DRAFT_MAP_KEY,
  DRAFT_NEW_KEY,
  draftStorageKey,
  parseDraftMap,
  readComposerDraft,
  writeComposerDraft,
} from '@/lib/composerDraft';

describe('composerDraft', () => {
  afterEach(() => {
    localStorage.removeItem(COMPOSER_DRAFT_KEY);
    localStorage.removeItem(COMPOSER_DRAFT_MAP_KEY);
  });

  it('sohbet anahtarını ayırır, boşu siler', () => {
    expect(draftStorageKey(null)).toBe(DRAFT_NEW_KEY);
    expect(draftStorageKey(' abc ')).toBe('abc');
    writeComposerDraft('  merhaba  ', 'c1');
    expect(readComposerDraft('c1')).toBe('  merhaba  ');
    expect(readComposerDraft('c2')).toBe('');
    writeComposerDraft('   ', 'c1');
    expect(readComposerDraft('c1')).toBe('');
  });

  it('eski tek anahtarı new altına taşır', () => {
    localStorage.setItem(COMPOSER_DRAFT_KEY, 'eski');
    expect(readComposerDraft(null)).toBe('eski');
    expect(localStorage.getItem(COMPOSER_DRAFT_KEY)).toBeNull();
    expect(parseDraftMap(localStorage.getItem(COMPOSER_DRAFT_MAP_KEY))[DRAFT_NEW_KEY]).toBe(
      'eski',
    );
  });
});
