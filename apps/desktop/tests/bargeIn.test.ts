import { describe, expect, it } from 'vitest';

import { spokenAssistantContent, spokenFromPlayback, trimLiveAssistant } from '@/lib/bargeIn';

describe('spokenAssistantContent', () => {
  it('söylenmemiş cümleyi keser', () => {
    expect(
      spokenAssistantContent('Merhaba dünya. Nasılsın?', 'Merhaba dünya.'),
    ).toBe('Merhaba dünya.');
  });

  it('henüz ses yoksa boş döner', () => {
    expect(spokenAssistantContent('Merhaba dünya. Nasılsın?', '')).toBe('');
  });

  it('kısmi cümleyi prefix olarak tutar', () => {
    expect(spokenAssistantContent('Merhaba dünya.', 'Merhaba')).toBe('Merhaba');
  });
});

describe('spokenFromPlayback', () => {
  it('biten parçalar + mevcut kesit', () => {
    expect(spokenFromPlayback(['Merhaba.'], 'ABCDEFGH', 0.5)).toBe('Merhaba. ABCD');
  });

  it('kesit sıfırsa yalnız bitenler', () => {
    expect(spokenFromPlayback(['Merhaba.'], 'Nasılsın?', 0)).toBe('Merhaba.');
  });
});

describe('trimLiveAssistant', () => {
  it('akan metni ve son asistan balonunu söylenenle keser', () => {
    const result = trimLiveAssistant({
      streamContent: 'Merhaba dünya. Nasılsın?',
      messages: [
        { id: 'u', role: 'user', content: 'selam' },
        { id: 'a', role: 'assistant', content: 'Merhaba dünya. Nasılsın?' },
      ],
      spoken: 'Merhaba dünya.',
    });
    expect(result.streamContent).toBe('Merhaba dünya.');
    expect(result.messages[1]?.content).toBe('Merhaba dünya.');
  });

  it('asistan balonu yoksa yalnız akışı keser', () => {
    const result = trimLiveAssistant({
      streamContent: 'Merhaba dünya. Nasılsın?',
      messages: [{ id: 'u', role: 'user', content: 'selam' }],
      spoken: 'Merhaba dünya.',
    });
    expect(result.streamContent).toBe('Merhaba dünya.');
    expect(result.messages).toHaveLength(1);
  });
});
