/**
 * Chatbox `quoteMsg` + InputBox: satırları `> ` ile alıntıla, taslağa ekle.
 * Boş kutuya yapıştırır; doluysa iki satır boşluk bırakır.
 */

export const QUOTE_SEPARATOR = '-------------------';

export function formatQuotedMessage(text: string): string | null {
  const normalized = text.replace(/\r\n/g, '\n').replace(/\s+$/u, '');
  if (!normalized.trim()) return null;
  const quoted = normalized
    .split('\n')
    .map((line) => `> ${line}`)
    .join('\n');
  return `${quoted}\n\n${QUOTE_SEPARATOR}\n\n`;
}

export function mergeQuoteIntoDraft(current: string, quote: string): string {
  if (!quote) return current;
  if (!current) return quote;
  const trailing = current.match(/(\n)+$/)?.[0].length ?? 0;
  return current + '\n'.repeat(Math.max(0, 2 - trailing)) + quote;
}
