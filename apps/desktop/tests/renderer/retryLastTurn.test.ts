import { describe, expect, it } from 'vitest';

import { canRetryLastTurn, lastUserPrompt } from '@/lib/retryLastTurn';

describe('retryLastTurn', () => {
  it('son dolu kullanıcı metnini alır', () => {
    expect(
      lastUserPrompt([
        { role: 'user', content: 'ilk' },
        { role: 'assistant', content: 'cevap' },
        { role: 'user', content: '  GPU nedir  ' },
        { role: 'assistant', content: 'ok' },
      ]),
    ).toBe('GPU nedir');
    expect(lastUserPrompt([{ role: 'assistant', content: 'x' }])).toBe('');
  });

  it('üretimde veya son mesaj kullanıcıyken kapalı', () => {
    const done = [
      { role: 'user', content: 'sor' },
      { role: 'assistant', content: 'yanıt' },
    ];
    expect(canRetryLastTurn({ generating: false, messages: done })).toBe(true);
    expect(canRetryLastTurn({ generating: true, messages: done })).toBe(false);
    expect(
      canRetryLastTurn({
        generating: false,
        messages: [{ role: 'user', content: 'sor' }],
      }),
    ).toBe(false);
    expect(canRetryLastTurn({ generating: false, messages: [] })).toBe(false);
  });
});
