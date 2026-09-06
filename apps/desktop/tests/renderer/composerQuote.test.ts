import { describe, expect, it } from 'vitest';

import { formatQuotedMessage, mergeQuoteIntoDraft, QUOTE_SEPARATOR } from '@/lib/composerQuote';

describe('composerQuote', () => {
  it('boşu atar, satırları > ile sarar', () => {
    expect(formatQuotedMessage('   ')).toBeNull();
    expect(formatQuotedMessage('GPU\ndurumu')).toBe(
      `> GPU\n> durumu\n\n${QUOTE_SEPARATOR}\n\n`,
    );
  });

  it('boş taslağa yapıştırır, doluya iki satır ekler', () => {
    const quote = formatQuotedMessage('al') ?? '';
    expect(mergeQuoteIntoDraft('', quote)).toBe(quote);
    expect(mergeQuoteIntoDraft('soru', quote)).toBe(`soru\n\n${quote}`);
    expect(mergeQuoteIntoDraft('soru\n', quote)).toBe(`soru\n\n${quote}`);
  });
});
