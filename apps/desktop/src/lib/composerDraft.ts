/**
 * AnythingLLM `USER_PROMPT_INPUT_MAP` — taslak sohbet kimliğine göre.
 * Page Assist `persistChatInput`: gönderilmemiş metin durur, gönderince silinir.
 * Eski tek anahtar `uryx.composer.draft` bir kez `new` altına taşınır.
 */

export const COMPOSER_DRAFT_KEY = 'uryx.composer.draft';
export const COMPOSER_DRAFT_MAP_KEY = 'uryx.composer.drafts';
export const DRAFT_NEW_KEY = 'new';
export const DRAFT_MAP_CAP = 24;
const DRAFT_MAX = 8_000;

export function draftStorageKey(conversationId?: string | null): string {
  const id = (conversationId ?? '').trim();
  return id || DRAFT_NEW_KEY;
}

export function parseDraftMap(raw: string | null): Record<string, string> {
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {};
    const map: Record<string, string> = {};
    for (const [key, value] of Object.entries(parsed)) {
      if (typeof value === 'string' && value.trim()) map[key] = value.slice(0, DRAFT_MAX);
    }
    return map;
  } catch {
    return {};
  }
}

function readMap(): Record<string, string> {
  if (typeof localStorage === 'undefined') return {};
  try {
    const map = parseDraftMap(localStorage.getItem(COMPOSER_DRAFT_MAP_KEY));
    const legacy = localStorage.getItem(COMPOSER_DRAFT_KEY);
    if (legacy && legacy.trim() && !map[DRAFT_NEW_KEY]) {
      map[DRAFT_NEW_KEY] = legacy.slice(0, DRAFT_MAX);
      localStorage.setItem(COMPOSER_DRAFT_MAP_KEY, JSON.stringify(map));
      localStorage.removeItem(COMPOSER_DRAFT_KEY);
    }
    return map;
  } catch {
    return {};
  }
}

function writeMap(map: Record<string, string>): void {
  if (typeof localStorage === 'undefined') return;
  try {
    const keys = Object.keys(map);
    if (keys.length > DRAFT_MAP_CAP) {
      for (const key of keys.slice(0, keys.length - DRAFT_MAP_CAP)) {
        delete map[key];
      }
    }
    if (Object.keys(map).length === 0) {
      localStorage.removeItem(COMPOSER_DRAFT_MAP_KEY);
      return;
    }
    localStorage.setItem(COMPOSER_DRAFT_MAP_KEY, JSON.stringify(map));
  } catch {
  }
}

export function readComposerDraft(conversationId?: string | null): string {
  return readMap()[draftStorageKey(conversationId)] ?? '';
}

export function writeComposerDraft(text: string, conversationId?: string | null): void {
  const key = draftStorageKey(conversationId);
  const map = readMap();
  const trimmed = text.slice(0, DRAFT_MAX);
  if (!trimmed.trim()) {
    delete map[key];
  } else {
    map[key] = trimmed;
  }
  writeMap(map);
}
