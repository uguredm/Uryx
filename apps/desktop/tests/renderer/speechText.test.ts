import { describe, expect, it } from 'vitest';

import { cleanSpeechText } from '../../src/lib/speechText';

describe('cleanSpeechText', () => {
  it('removes visual markup, source lines, and URLs', () => {
    const text = [
      'İşte bulduğum görseller:',
      '![Örnek](https://example.com/photo.jpg)',
      '*Kaynak: [Örnek Site](https://example.com/page)*',
      'Detaylar için https://example.com adresine bakabilirsin.',
    ].join('\n');

    expect(cleanSpeechText(text)).toBe(
      'İşte bulduğum görseller: Detaylar için adresine bakabilirsin.',
    );
  });
});
