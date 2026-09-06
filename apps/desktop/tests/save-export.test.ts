/** LobeChat kaydet diyalogu — yol renderer'dan gelmez. */

import { describe, expect, it } from 'vitest';

import {
  ensureMarkdownPath,
  parseSaveTextPayload,
  sanitizeSaveFilename,
  SAVE_TEXT_MAX_CHARS,
} from '../electron/save-export';

describe('native kaydet', () => {
  it('adını temizler ve .md ekler', () => {
    expect(sanitizeSaveFilename('a/b\\c:d')).toBe('a b c d.md');
    expect(sanitizeSaveFilename('not.md')).toBe('not.md');
    expect(sanitizeSaveFilename('  ', 'tr')).toBe('Sohbet.md');
    expect(sanitizeSaveFilename('  ')).toBe('chat.md');
  });

  it('seçilen yola .md zorlar', () => {
    expect(ensureMarkdownPath('C:\\Users\\me\\sohbet')).toBe('C:\\Users\\me\\sohbet.md');
    expect(ensureMarkdownPath('C:\\Users\\me\\sohbet.MD')).toBe('C:\\Users\\me\\sohbet.MD');
  });

  it('içerik tavanını aşınca yazmaz', () => {
    expect(() =>
      parseSaveTextPayload({ defaultName: 'x.md', content: 'a'.repeat(SAVE_TEXT_MAX_CHARS + 1) }, 'tr'),
    ).toThrow(/çok uzun/i);
    expect(parseSaveTextPayload({ defaultName: 'x.md', content: '# hi' })).toEqual({
      defaultName: 'x.md',
      content: '# hi',
    });
  });
});
