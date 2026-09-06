/**
 * big-AGI ScrollToBottom + Cherry Studio Messages:
 * kullanıcı yukarı kaydırdıysa akış aşağı çekmez; 60px kuralı.
 * Cherry column-reverse `scrollTo({ top: 0 })` çalınmadı.
 */

export const STICKY_MARGIN_PX = 60;

export type ScrollMetrics = {
  scrollHeight: number;
  scrollTop: number;
  clientHeight: number;
};

export function isNearBottom(metrics: ScrollMetrics, margin = STICKY_MARGIN_PX): boolean {
  return metrics.scrollHeight - metrics.scrollTop <= metrics.clientHeight + margin;
}

export function shouldAutoScroll(stickToBottom: boolean): boolean {
  return stickToBottom;
}

export function lastCopyableText(messages: Array<{ content?: string }>): string | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    const text = (messages[i]?.content ?? '').replace(/\s+$/u, '');
    if (text.trim()) return text;
  }
  return null;
}
