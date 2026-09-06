/**
 * LibreChat: pinned'i tarih grubundan çıkar, aramasız üstte tut.
 * https://github.com/danny-avila/LibreChat/blob/main/client/src/utils/convos.ts
 * https://github.com/danny-avila/LibreChat/blob/main/client/src/components/Conversations/Conversations.tsx
 * Open WebUI: tek `pinnedChats` store — oda değişince her oda duyar.
 * https://github.com/open-webui/open-webui/blob/main/src/lib/stores/index.ts
 * https://github.com/open-webui/open-webui/blob/main/src/lib/stores/chatList.ts
 * https://github.com/open-webui/open-webui/blob/main/src/lib/components/layout/Sidebar/ChatMenu.svelte
 * API pin yok (R&D 2); localStorage + zustand. Tavan 12.
 */

import { create } from 'zustand';

export const PINNED_CHATS_KEY = 'uryx.history.pinned';
export const PINNED_CHATS_CAP = 12;

const ID_RE = /^[a-zA-Z0-9_-]{1,80}$/;

export function sanitizePinnedId(id: string): string | null {
  const trimmed = id.trim();
  return ID_RE.test(trimmed) ? trimmed : null;
}

export function parsePinnedIds(raw: string | null): string[] {
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    const seen = new Set<string>();
    const ids: string[] = [];
    for (const item of parsed) {
      if (typeof item !== 'string') continue;
      const id = sanitizePinnedId(item);
      if (!id || seen.has(id)) continue;
      seen.add(id);
      ids.push(id);
      if (ids.length >= PINNED_CHATS_CAP) break;
    }
    return ids;
  } catch {
    return [];
  }
}

export function readPinnedIds(): string[] {
  if (typeof localStorage === 'undefined') return [];
  try {
    return parsePinnedIds(localStorage.getItem(PINNED_CHATS_KEY));
  } catch {
    return [];
  }
}

export function writePinnedIds(ids: string[]): string[] {
  const next = parsePinnedIds(JSON.stringify(ids));
  if (typeof localStorage === 'undefined') return next;
  try {
    if (next.length === 0) localStorage.removeItem(PINNED_CHATS_KEY);
    else localStorage.setItem(PINNED_CHATS_KEY, JSON.stringify(next));
  } catch {
  }
  return next;
}

export function togglePinnedId(id: string, current = readPinnedIds()): string[] {
  const clean = sanitizePinnedId(id);
  if (!clean) return writePinnedIds(current);
  const without = current.filter((item) => item !== clean);
  if (without.length !== current.length) return writePinnedIds(without);
  return writePinnedIds([clean, ...without].slice(0, PINNED_CHATS_CAP));
}

export function unpinId(id: string, current = readPinnedIds()): string[] {
  return writePinnedIds(current.filter((item) => item !== id));
}

export function splitPinnedConversations<T extends { id: string }>(
  items: T[],
  pinnedIds: string[],
): { pinned: T[]; rest: T[] } {
  const byId = new Map(items.map((item) => [item.id, item]));
  const pinned: T[] = [];
  const pinnedSet = new Set<string>();
  for (const id of pinnedIds) {
    const hit = byId.get(id);
    if (!hit) continue;
    pinned.push(hit);
    pinnedSet.add(id);
  }
  return {
    pinned,
    rest: items.filter((item) => !pinnedSet.has(item.id)),
  };
}

/** Open WebUI `$pinnedChats` — HUD ve History aynı dizi. */
export const usePinnedChatsStore = create<{
  ids: string[];
  toggle: (id: string) => void;
  unpin: (id: string) => void;
  hydrate: () => void;
}>((set, get) => ({
  ids: readPinnedIds(),
  toggle: (id) => set({ ids: togglePinnedId(id, get().ids) }),
  unpin: (id) => set({ ids: unpinId(id, get().ids) }),
  hydrate: () => set({ ids: readPinnedIds() }),
}));
