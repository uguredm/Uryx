/**
 * Allowlist'li Electron hızlandırıcıları.
 *
 * Win / Super / Meta yasak (Windows tuşu çalınmaz).
 * Global kısayol en az Control + izinli bir tuş ister.
 */

const FORBIDDEN_MOD = /^(super|meta|win|windows|cmd|command)$/i;
const ALLOWED_MOD = new Set(['control', 'ctrl', 'shift', 'alt', 'option', 'commandorcontrol']);
const ALLOWED_KEY =
  /^(?:[A-Z0-9]|F(?:[1-9]|1[0-2])|Space|Tab|Enter|Escape|Plus|Minus|Up|Down|Left|Right)$/i;

export const DEFAULT_WINDOW_ACCELERATOR = 'Control+Shift+J';
export const DEFAULT_PTT_KEY = 'Space';

/** Sabit ek eylemler — model kaydedemez; Win+ yok. */
export const EXTRA_HOST_HOTKEYS = [
  { accelerator: 'Control+Shift+N', action: 'newChat' as const },
  { accelerator: 'Control+Shift+D', action: 'openSystem' as const },
] as const;

export interface ParsedAccelerator {
  mods: string[];
  key: string;
}

function normalizeKey(key: string): string {
  if (key.length === 1) return key.toUpperCase();
  return key.charAt(0).toUpperCase() + key.slice(1);
}

function normalizeMods(mods: string[]): string[] {
  const mapped = mods.map((mod) => {
    const lower = mod.toLowerCase();
    if (lower === 'ctrl' || lower === 'control' || lower === 'commandorcontrol') return 'Control';
    if (lower === 'shift') return 'Shift';
    if (lower === 'alt' || lower === 'option') return 'Alt';
    return mod;
  });
  return [...new Set(mapped)];
}

/** Ham hızlandırıcıyı parçalar; Win/Super veya izinsiz tuşta null. */
export function parseAccelerator(raw: unknown): ParsedAccelerator | null {
  const parts = String(raw ?? '')
    .split('+')
    .map((part) => part.trim())
    .filter(Boolean);
  if (parts.length < 2) return null;
  const key = parts[parts.length - 1] ?? '';
  const mods = parts.slice(0, -1);
  if (mods.some((mod) => FORBIDDEN_MOD.test(mod))) return null;
  if (!mods.every((mod) => ALLOWED_MOD.has(mod.toLowerCase()))) return null;
  if (!ALLOWED_KEY.test(key)) return null;
  if (!mods.some((mod) => /^(control|ctrl|commandorcontrol)$/i.test(mod))) return null;
  return { mods: normalizeMods(mods), key: normalizeKey(key) };
}

export function formatAccelerator(parsed: ParsedAccelerator): string {
  return [...parsed.mods, parsed.key].join('+');
}

/** Kayıt/ayar için güvenli hızlandırıcı; geçersizse fallback. */
export function sanitizeAccelerator(raw: unknown, fallback = DEFAULT_WINDOW_ACCELERATOR): string {
  const parsed = parseAccelerator(raw) ?? parseAccelerator(fallback);
  if (!parsed) return DEFAULT_WINDOW_ACCELERATOR;
  return formatAccelerator(parsed);
}

/** Push-to-talk tuş parçası (Win/Super yok). */
export function sanitizePushToTalkKey(raw: unknown, fallback = DEFAULT_PTT_KEY): string {
  const key = String(raw ?? '').trim();
  if (ALLOWED_KEY.test(key) && !FORBIDDEN_MOD.test(key)) {
    return normalizeKey(key);
  }
  if (ALLOWED_KEY.test(String(fallback))) return normalizeKey(String(fallback));
  return DEFAULT_PTT_KEY;
}

export function pushToTalkAccelerator(key: unknown): string {
  return sanitizeAccelerator(
    `Control+Shift+${sanitizePushToTalkKey(key)}`,
    `Control+Shift+${DEFAULT_PTT_KEY}`,
  );
}
