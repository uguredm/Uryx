/**
 * Cody HistoryTab + PearAI history TableRow: satır içi başlık.
 * PATCH zaten `api.conversations.rename`.
 */

export const RENAME_TITLE_MAX = 120;

export function sanitizeRenameTitle(title: string): string | null {
  const trimmed = title.replace(/\s+/g, ' ').trim();
  if (!trimmed) return null;
  return trimmed.slice(0, RENAME_TITLE_MAX);
}
