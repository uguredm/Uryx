/**
 * Yeniden bağlanma süre penceresi.
 *
 * VS Code `ReconnectionShortGraceTime` = 5dk (uzun 3s çalınmadı — yerel API).
 * `Date.now() - loopStartTime >= graceTime` → permanent.
 */

/** ipc.net `ReconnectionShortGraceTime`. */
export const HOST_RECONNECT_GRACE_MS = 5 * 60 * 1000;

export function shouldGiveUpReconnectAfterGrace(
  loopStartAt: number | null,
  now: number,
  graceMs = HOST_RECONNECT_GRACE_MS,
): boolean {
  if (loopStartAt == null) return false;
  return now - loopStartAt >= graceMs;
}
