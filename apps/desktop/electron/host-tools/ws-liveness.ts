/**
 * Yarım açık `/ws/host` soketi.
 *
 * VS Code `_keepAliveTimeoutCheck`: gelen veri yoksa ölü.
 * `ws` FAQ: `pong` gelmezse `terminate()` — `close()` close timer bekler.
 */

/** İki 20s ping + gecikme. VS Code TimeoutTime 20s (5s keepalive). */
export const HOST_STALE_SILENCE_MS = 45_000;

/** `lastAliveAt` yoksa henüz açılmamış — kesme. */
export function shouldTerminateStaleSocket(
  now: number,
  lastAliveAt: number | null,
  maxSilenceMs = HOST_STALE_SILENCE_MS,
): boolean {
  if (lastAliveAt == null) return false;
  return now - lastAliveAt >= maxSilenceMs;
}
