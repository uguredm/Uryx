import { describe, expect, it } from 'vitest';

import { applyComposerRecall, userPromptsNewestFirst } from '@/lib/composerRecall';

const history = userPromptsNewestFirst([
  { role: 'user', content: 'ilk' },
  { role: 'assistant', content: 'tamam' },
  { role: 'user', content: 'Spotify aç' },
]);

describe('composerRecall', () => {
  it('kullanıcı mesajlarını yeniden eskiye dizer', () => {
    expect(history).toEqual(['Spotify aç', 'ilk']);
  });

  it('boş kutuda yukarı son kullanıcıyı getirir, taslağı ezmez', () => {
    expect(applyComposerRecall('', history, 'ArrowUp', '')).toEqual({
      text: 'Spotify aç',
      recalled: 'Spotify aç',
    });
    expect(applyComposerRecall('yarım taslak', history, 'ArrowUp', '')).toBeNull();
  });

  it('yukarı daha eskiye, aşağı boşaltır', () => {
    const older = applyComposerRecall('Spotify aç', history, 'ArrowUp', 'Spotify aç');
    expect(older).toEqual({ text: 'ilk', recalled: 'ilk' });
    expect(applyComposerRecall('ilk', history, 'ArrowDown', 'ilk')).toEqual({
      text: 'Spotify aç',
      recalled: 'Spotify aç',
    });
    expect(applyComposerRecall('Spotify aç', history, 'ArrowDown', 'Spotify aç')).toEqual({
      text: '',
      recalled: '',
    });
  });
});
