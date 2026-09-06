/**
 * `/ws/host` yeniden bağlanma gecikmesi.
 *
 * VS Code `TIMES` (saniye) — ilk tur 0, sonra 5…30.
 * botocore `ExponentialBackoff`: `t_i = rand(0,1) * min(cap, MAX)` (full jitter).
 */

/** VS Code `TIMES` saniye → ms. */
export const HOST_RECONNECT_TIMES_MS = [0, 5_000, 5_000, 10_000, 10_000, 10_000, 10_000, 10_000, 30_000];

/** `attempt` 1-tabanlı. `random` test için enjekte. */
export function reconnectDelayMs(attempt: number, random: () => number = Math.random): number {
  const index = Math.min(Math.max(Math.floor(attempt), 1) - 1, HOST_RECONNECT_TIMES_MS.length - 1);
  const cap = HOST_RECONNECT_TIMES_MS[index] ?? 0;
  if (cap <= 0) return 0;
  const unit = Math.min(Math.max(random(), 0), 1);
  return Math.floor(unit * cap);
}
