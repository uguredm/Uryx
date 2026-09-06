/**
 * Uyku sonrası host köprüsü.
 *
 * VS Code `onDidResumeOS` = `powerMonitor` `resume`.
 * Tunnel `_resumeReconnects` hız kapısı — Windows çift `resume` (Electron #44252) yutulsun.
 */

export const POWER_RESUME_DEBOUNCE_MS = 2500;

/** Çift `resume` hemen ikinci reconnect açmasın. */
export function shouldForceReconnectOnResume(
  now: number,
  lastResumeAt: number | null,
  minGapMs = POWER_RESUME_DEBOUNCE_MS,
): boolean {
  if (lastResumeAt == null) return true;
  return now - lastResumeAt >= minGapMs;
}

/** Uykudayken backoff zamanlayıcısı kurulmasın (timer uyku boyunca donar). */
export function shouldScheduleReconnectWhileAwake(suspended: boolean, stopped: boolean): boolean {
  return !suspended && !stopped;
}
