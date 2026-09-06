/**
 * Kalıcı close — yeniden bağlanma yok.
 *
 * VS Code `triggerPermanentFailure` / `VSCODE_CONNECTION_ERROR`.
 * discord.js `AuthenticationFailed` (4004) `recover` yok.
 * Uryx API `4401` = HTTP 401 analog.
 */

export const HOST_AUTH_CLOSE_CODE = 4401;

/** Auth/policy close: aynı token ile backoff yağmasın. */
export function shouldGiveUpHostReconnect(code: number): boolean {
  return code === HOST_AUTH_CLOSE_CODE;
}
