import { describe, expect, it } from 'vitest';

import { matchComposerSlash, parseComposerInput, unescapeComposerSlash } from '@/lib/composerSlash';

describe('composerSlash', () => {
  it('TheLounge: // kaçış, bilinen /komut, yol yutulmaz', () => {
    expect(unescapeComposerSlash('//yeni')).toBe('/yeni');
    expect(matchComposerSlash('/yeni')).toBe('newChat');
    expect(matchComposerSlash('/DURDUR')).toBe('stop');
    expect(matchComposerSlash('/ayarlar')).toBe('settings');
    expect(matchComposerSlash('/ara')).toBe('historySearch');
    expect(matchComposerSlash('/tmp/foo')).toBeNull();
    expect(matchComposerSlash('//yeni')).toBeNull();
    expect(parseComposerInput('//path')).toEqual({ send: '/path' });
    expect(parseComposerInput('/new')).toEqual({ slash: 'newChat' });
    expect(parseComposerInput('merhaba')).toEqual({ send: 'merhaba' });
  });
});
