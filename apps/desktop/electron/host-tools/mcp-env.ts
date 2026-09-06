/**
 * MCP çocuk ortamı.
 *
 * SDK `getDefaultEnvironment`: yalnız allowlist; `()` fonksiyon değerleri yok.
 * VS Code `removeDangerousEnvVariables`: NODE_OPTIONS / LD_PRELOAD / DEBUG.
 * Win32: SDK listesine PATHEXT/COMSPEC/TMP (cmd.exe + npx).
 */

import { MCP_SERVER_ENV_KEYS as MCP_SERVER_ENV_KEY_LIST } from '@shared/settings';

export const MCP_INHERITED_ENV_WIN = [
  'APPDATA',
  'HOMEDRIVE',
  'HOMEPATH',
  'LOCALAPPDATA',
  'PATH',
  'PATHEXT',
  'COMSPEC',
  'PROCESSOR_ARCHITECTURE',
  'SYSTEMDRIVE',
  'SYSTEMROOT',
  'TEMP',
  'TMP',
  'USERNAME',
  'USERPROFILE',
  'PROGRAMFILES',
  'PROGRAMFILES(X86)',
  'WINDIR',
] as const;

export const MCP_INHERITED_ENV_UNIX = ['HOME', 'LANG', 'LC_ALL', 'LOGNAME', 'PATH', 'SHELL', 'TERM', 'USER'] as const;

/** Süreç PATH/HOME satır sonu — tüm PATH'i atma, ilk satırı tut. Tırnaklı PATH ENOENT olmasın. */
export function sanitizeInheritedEnvValue(value: string): string | undefined {
  if (value.startsWith('()') || value.includes('\0')) return undefined;
  let first = value.split(/[\r\n]/, 1)[0]?.trim() ?? '';
  if (first.length >= 2) {
    const quote = first[0];
    if ((quote === '"' || quote === "'") && first.endsWith(quote)) {
      first = first.slice(1, -1).trim();
    }
  }
  return first || undefined;
}

const DANGEROUS_ENV = new Set([
  'DEBUG',
  'NODE_OPTIONS',
  'VSCODE_NODE_OPTIONS',
  'NPM_CONFIG_NODE_OPTIONS',
  'ELECTRON_RUN_AS_NODE',
  'LD_PRELOAD',
  'LD_LIBRARY_PATH',
  'DYLD_INSERT_LIBRARIES',
  'DYLD_LIBRARY_PATH',
  'DYLD_FALLBACK_LIBRARY_PATH',
  'GH_TOKEN',
  'GITHUB_TOKEN',
  'HTTP_PROXY',
  'HTTPS_PROXY',
  'ALL_PROXY',
]);

/** Ayar JSON'undan çocuğa geçebilen anahtarlar — süreç ortamından kopyalanmaz. */
export const MCP_SERVER_ENV_KEYS = new Set<string>(MCP_SERVER_ENV_KEY_LIST);

export function sanitizeMcpServerEnv(value: unknown): Record<string, string> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  const env: Record<string, string> = {};
  for (const [rawKey, rawValue] of Object.entries(value as Record<string, unknown>).slice(0, 16)) {
    const key = rawKey.trim().toUpperCase();
    if (!MCP_SERVER_ENV_KEYS.has(key) || DANGEROUS_ENV.has(key)) continue;
    const raw = String(rawValue ?? '');
    if (/[\0\r\n]/.test(raw)) continue;
    const next = raw.trim().slice(0, 500);
    if (!next || next.startsWith('()')) continue;
    env[key] = next;
  }
  return env;
}

export function mcpSafePathext(value: string | undefined): string {
  const allowed = new Set(['.COM', '.EXE', '.BAT', '.CMD']);
  const parts = String(value ?? '')
    .split(';')
    .map((part) => part.trim().toLocaleUpperCase('en-US'))
    .filter((part) => allowed.has(part));
  return parts.length > 0 ? [...new Set(parts)].join(';') : '.COM;.EXE;.BAT;.CMD';
}

export function mcpFallbackPath(
  platform: NodeJS.Platform,
  env: NodeJS.ProcessEnv = {},
): string {
  if (platform === 'win32') {
    const root = sanitizeInheritedEnvValue(String(env.SYSTEMROOT || env.WINDIR || 'C:\\Windows')) || 'C:\\Windows';
    return `${root}\\System32;${root}`;
  }
  return '/usr/bin:/bin';
}

export function mcpInheritedKeys(platform: NodeJS.Platform = process.platform): readonly string[] {
  return platform === 'win32' ? MCP_INHERITED_ENV_WIN : MCP_INHERITED_ENV_UNIX;
}

function lookupEnv(source: NodeJS.ProcessEnv, key: string): string | undefined {
  const direct = source[key];
  if (direct !== undefined) return direct;
  const found = Object.keys(source).find((item) => item.toUpperCase() === key.toUpperCase());
  return found ? source[found] : undefined;
}

/** Allowlist + tehlikeli anahtar yok; Python stdio tamponu / UTF-8 sabit. */
export function mcpChildEnv(
  source: NodeJS.ProcessEnv = process.env,
  platform: NodeJS.Platform = process.platform,
  extra: Record<string, string> = {},
): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = {};
  for (const key of mcpInheritedKeys(platform)) {
    if (DANGEROUS_ENV.has(key.toUpperCase())) continue;
    const value = lookupEnv(source, key);
    if (value === undefined || value === '') continue;
    const cleaned = sanitizeInheritedEnvValue(value);
    if (!cleaned) continue;
    env[key] = cleaned;
  }
  for (const [key, value] of Object.entries(sanitizeMcpServerEnv(extra))) {
    env[key] = value;
  }
  if (!env.PATH) {
    const fallback = mcpFallbackPath(platform, env);
    if (fallback) env.PATH = fallback;
  }
  if (platform === 'win32') {
    env.PATHEXT = mcpSafePathext(env.PATHEXT);
  }
  if (platform === 'win32') {
    const root = env.SYSTEMROOT || env.WINDIR || 'C:\\Windows';
    env.COMSPEC = `${root}\\System32\\cmd.exe`;
    env.NoDefaultCurrentDirectoryInExePath = '1';
  }
  if (platform === 'win32' && !env.TEMP && !env.TMP) {
    const local = env.LOCALAPPDATA;
    const root = env.SYSTEMROOT || env.WINDIR || 'C:\\Windows';
    const temp = local ? `${local}\\Temp` : `${root}\\Temp`;
    env.TEMP = temp;
    env.TMP = temp;
  } else if (platform === 'win32' && !env.TEMP && env.TMP) {
    env.TEMP = env.TMP;
  } else if (platform === 'win32' && !env.TMP && env.TEMP) {
    env.TMP = env.TEMP;
  }
  if (platform === 'win32' && !env.HOME && env.USERPROFILE) {
    env.HOME = env.USERPROFILE;
  }
  if (platform !== 'win32' && !env.LANG && !env.LC_ALL) {
    env.LANG = 'C.UTF-8';
  }
  env.PYTHONIOENCODING = 'utf-8';
  env.PYTHONUTF8 = '1';
  env.PYTHONUNBUFFERED = '1';
  env.PYTHONSAFEPATH = '1';
  env.PYTHONDONTWRITEBYTECODE = '1';
  env.npm_config_yes = 'true';
  env.npm_config_update_notifier = 'false';
  env.NO_COLOR = '1';
  env.FORCE_COLOR = '0';
  return env;
}
