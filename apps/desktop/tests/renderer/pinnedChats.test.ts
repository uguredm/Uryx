import { afterEach, describe, expect, it } from 'vitest';

import {
  PINNED_CHATS_CAP,
  PINNED_CHATS_KEY,
  parsePinnedIds,
  splitPinnedConversations,
  togglePinnedId,
  usePinnedChatsStore,
  writePinnedIds,
} from '@/lib/pinnedChats';

describe('pinnedChats', () => {
  afterEach(() => {
    localStorage.removeItem(PINNED_CHATS_KEY);
    usePinnedChatsStore.setState({ ids: [] });
  });

  it('bozuk JSON ve tekrarları atar', () => {
    expect(parsePinnedIds('nope')).toEqual([]);
    expect(parsePinnedIds('["a","a","bad id!",""]')).toEqual(['a']);
  });

  it('sabiti üste alır, ikinci tık çözer, tavan keser', () => {
    const first = togglePinnedId('conv-1', []);
    expect(first).toEqual(['conv-1']);
    expect(togglePinnedId('conv-1', first)).toEqual([]);

    const overflow = Array.from({ length: PINNED_CHATS_CAP }, (_, i) => `id${i}`);
    writePinnedIds(overflow);
    const next = togglePinnedId('yeni');
    expect(next[0]).toBe('yeni');
    expect(next).toHaveLength(PINNED_CHATS_CAP);
    expect(next).not.toContain('id11');
  });

  it('LibreChat gibi sabitleri tarih listesinden ayırır', () => {
    const items = [
      { id: 'old', title: 'eski' },
      { id: 'keep', title: 'sabit' },
    ];
    const { pinned, rest } = splitPinnedConversations(items, ['keep', 'ghost']);
    expect(pinned.map((item) => item.id)).toEqual(['keep']);
    expect(rest.map((item) => item.id)).toEqual(['old']);
  });

  it('HUD ve History aynı store dizisini görür', () => {
    usePinnedChatsStore.setState({ ids: [] });
    usePinnedChatsStore.getState().toggle('hud-1');
    const historyView = usePinnedChatsStore.getState().ids;
    const hudView = usePinnedChatsStore.getState().ids;
    expect(historyView).toEqual(['hud-1']);
    expect(hudView).toBe(historyView);
  });
});
