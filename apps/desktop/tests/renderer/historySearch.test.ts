import { describe, expect, it } from 'vitest';
import type { ConversationSummary } from '@shared/api';

import {
  extractSearchSnippet,
  groupConversations,
  historyBucket,
  messageMatchesQuery,
  searchHitWithNeighbors,
  splitHighlight,
  stepHistoryIndex,
} from '@/lib/historySearch';

const now = new Date('2026-08-16T12:00:00+03:00');

function conv(id: string, updated: string): ConversationSummary {
  return {
    id,
    title: `Sohbet ${id}`,
    created_at: updated,
    updated_at: updated,
    message_count: 2,
    archived: false,
  };
}

describe('historySearch', () => {
  it('günlere böler', () => {
    expect(historyBucket('2026-08-16T08:00:00+03:00', now)).toBe('today');
    expect(historyBucket('2026-08-15T18:00:00+03:00', now)).toBe('yesterday');
    expect(historyBucket('2026-08-12T18:00:00+03:00', now)).toBe('week');
    expect(historyBucket('2026-07-01T18:00:00+03:00', now)).toBe('older');
  });

  it('grup sırasını korur', () => {
    const groups = groupConversations(
      [
        conv('old', '2026-07-01T18:00:00+03:00'),
        conv('today', '2026-08-16T09:00:00+03:00'),
      ],
      now,
    );
    expect(groups.map((group) => group.bucket)).toEqual(['today', 'older']);
  });

  it('başlık eşleşmesini böler', () => {
    const parts = splitHighlight('Spotify aç', 'spot');
    expect(parts.some((part) => part.hit && part.text.toLocaleLowerCase('tr-TR') === 'spot')).toBe(
      true,
    );
  });

  it('HUD satır filtresi Türkçe büyük/küçük harf yutar', () => {
    expect(messageMatchesQuery('İstanbul hava', 'istanbul')).toBe(true);
    expect(messageMatchesQuery('merhaba', 'xyz')).toBe(false);
  });

  it('eşleşen mesajdan kesit çıkarır', () => {
    const snippet = extractSearchSnippet('Bugün Spotify aç ve sesi kıs', 'spotify');
    expect(snippet?.toLocaleLowerCase('tr-TR')).toContain('spotify');
  });

  it('Odysseus gibi hit + 1 komşu mesaj verir', () => {
    const hit = searchHitWithNeighbors(
      [
        { role: 'user', content: 'Spotify aç' },
        { role: 'assistant', content: 'Açıyorum, sesi de kısayım.' },
        { role: 'user', content: 'tamam' },
      ],
      'sesi',
    );
    expect(hit?.snippet.toLocaleLowerCase('tr-TR')).toContain('sesi');
    expect(hit?.before).toBe('Spotify aç');
    expect(hit?.after).toBe('tamam');
  });

  it('arama listesinde yukarı/aşağı sınırda durur', () => {
    expect(stepHistoryIndex(-1, 1, 3)).toBe(0);
    expect(stepHistoryIndex(0, 1, 3)).toBe(1);
    expect(stepHistoryIndex(2, 1, 3)).toBe(2);
    expect(stepHistoryIndex(-1, -1, 3)).toBe(2);
  });
});

