/**
 * Goose `ChatInput` queuedMessages — üretim sürerken sonraki mesaj kuyruğa girer.
 * hzaid01/Uryx `disabled={isActive}` çalınmadı: kutu kilitlenmez.
 */

export const COMPOSER_QUEUE_CAP = 8;

export function enqueueComposer(text: string, queue: string[]): string[] {
  const clean = text.replace(/\s+/g, ' ').trim();
  if (!clean) return queue;
  if (queue.length >= COMPOSER_QUEUE_CAP) return queue;
  return [...queue, clean];
}

export function shiftComposer(queue: string[]): { next?: string; rest: string[] } {
  if (!queue.length) return { rest: [] };
  const [next, ...rest] = queue;
  return { next, rest };
}
