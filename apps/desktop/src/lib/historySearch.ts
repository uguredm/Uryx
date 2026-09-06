/**
 * Open WebUI / LibreChat: sohbet listesini grupla, eşleşmeyi vurgula.
 * Sunucu başlık+içerik arar; renderer grup ve snippet üretir.
 */

import type { ConversationSummary } from '@shared/api';

export type HistoryBucket = 'today' | 'yesterday' | 'week' | 'older';

const BUCKET_ORDER: HistoryBucket[] = ['today', 'yesterday', 'week', 'older'];

export function startOfDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

export function historyBucket(iso: string, now = new Date()): HistoryBucket {
  const then = new Date(iso).getTime();
  if (!Number.isFinite(then)) return 'older';
  const today = startOfDay(now);
  const day = 86_400_000;
  if (then >= today) return 'today';
  if (then >= today - day) return 'yesterday';
  if (then >= today - 7 * day) return 'week';
  return 'older';
}

export function groupConversations(
  items: ConversationSummary[],
  now = new Date(),
): Array<{ bucket: HistoryBucket; items: ConversationSummary[] }> {
  const buckets = new Map<HistoryBucket, ConversationSummary[]>();
  for (const item of items) {
    const key = historyBucket(item.updated_at, now);
    const list = buckets.get(key) ?? [];
    list.push(item);
    buckets.set(key, list);
  }
  return BUCKET_ORDER.flatMap((bucket) => {
    const grouped = buckets.get(bucket);
    return grouped?.length ? [{ bucket, items: grouped }] : [];
  });
}

export function debounceMs(query: string, delay = 250): number {
  return query.trim().length < 2 ? 0 : delay;
}

/** Odysseus `search-chat.js` handleKeydown — sonuç listesinde yukarı/aşağı. */
export function stepHistoryIndex(current: number, delta: number, length: number): number {
  if (length <= 0) return -1;
  if (current < 0) return delta > 0 ? 0 : length - 1;
  return Math.max(0, Math.min(length - 1, current + delta));
}

export function copyPlainText(text: string): string {
  return text.replace(/\s+/g, ' ').trim();
}

export function splitHighlight(
  text: string,
  query: string,
): Array<{ text: string; hit: boolean }> {
  const needle = query.trim();
  if (!needle) return [{ text, hit: false }];
  const idx = text.toLocaleLowerCase('tr-TR').indexOf(needle.toLocaleLowerCase('tr-TR'));
  if (idx < 0) return [{ text, hit: false }];
  return [
    { text: text.slice(0, idx), hit: false },
    { text: text.slice(idx, idx + needle.length), hit: true },
    { text: text.slice(idx + needle.length), hit: false },
  ].filter((part) => part.text.length > 0);
}

export function messageMatchesQuery(content: string, query: string): boolean {
  const needle = query.trim().toLocaleLowerCase('tr-TR');
  if (!needle) return true;
  return content.toLocaleLowerCase('tr-TR').includes(needle);
}

export type SearchHit = {
  snippet: string;
  before?: string;
  after?: string;
};

/** Odysseus `session_search._context_for_message` — hit + 1 komşu. */
export function searchHitWithNeighbors(
  messages: Array<{ role: string; content: string }>,
  query: string,
): SearchHit | null {
  const idx = messages.findIndex((message) => extractSearchSnippet(message.content, query));
  if (idx < 0) return null;
  const snippet = extractSearchSnippet(messages[idx].content, query);
  if (!snippet) return null;
  const clip = (text: string): string => copyPlainText(text).slice(0, 72);
  const before = messages[idx - 1]?.content.trim();
  const after = messages[idx + 1]?.content.trim();
  return {
    snippet,
    before: before ? clip(before) : undefined,
    after: after ? clip(after) : undefined,
  };
}

/** LibreChat / Open WebUI: eşleşen mesajdan kısa kesit. */
export function extractSearchSnippet(content: string, query: string, radius = 52): string | null {
  const needle = query.trim();
  if (!needle || !content.trim()) return null;
  const hay = content.toLocaleLowerCase('tr-TR');
  const idx = hay.indexOf(needle.toLocaleLowerCase('tr-TR'));
  if (idx < 0) return null;
  const start = Math.max(0, idx - radius);
  const end = Math.min(content.length, idx + needle.length + radius);
  const slice = content.slice(start, end).replace(/\s+/g, ' ').trim();
  return `${start > 0 ? '…' : ''}${slice}${end < content.length ? '…' : ''}`;
}
