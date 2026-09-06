/**
 * TheLounge `input` / `inputLine`: `/` komut, `//` kaçış (tek / mesaj).
 * IRC say/join/lobby ve bilinmeyen komutu sunucuya yollama çalınmadı.
 */

export type ComposerSlash = 'newChat' | 'stop' | 'settings' | 'historySearch';

export function unescapeComposerSlash(text: string): string | null {
  if (text.startsWith('//')) return text.slice(1);
  return null;
}

export function matchComposerSlash(text: string): ComposerSlash | null {
  const trimmed = text.trim();
  if (!trimmed.startsWith('/') || trimmed.startsWith('//')) return null;
  if (/\s/.test(trimmed)) return null;
  const cmd = trimmed.slice(1).toLocaleLowerCase('tr-TR');
  if (cmd === 'yeni' || cmd === 'new') return 'newChat';
  if (cmd === 'durdur' || cmd === 'stop') return 'stop';
  if (cmd === 'ayarlar' || cmd === 'settings') return 'settings';
  if (cmd === 'ara' || cmd === 'search') return 'historySearch';
  return null;
}

export function parseComposerInput(
  text: string,
): { slash: ComposerSlash } | { send: string } {
  const trimmed = text.trim();
  const escaped = unescapeComposerSlash(trimmed);
  if (escaped !== null) return { send: escaped };
  const slash = matchComposerSlash(trimmed);
  if (slash) return { slash };
  return { send: trimmed };
}
