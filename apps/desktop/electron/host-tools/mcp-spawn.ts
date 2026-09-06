/**
 * Windows MCP spawn.
 *
 * Continue: `npx`/`uvx` batch → `cmd.exe /c` (WSL remote çalınmadı).
 * Node: `cmd.exe` `/d /s /c` — `shell: true` yok (CVE-2024-27980).
 */

import fs from 'node:fs';
import path from 'node:path';

import { hostText } from '../host-i18n';

/** Continue `WINDOWS_BATCH_COMMANDS` — allowlist kesişimi. */
const WINDOWS_BATCH_STEMS = new Set(['npx', 'npm', 'pnpm', 'pnpx', 'yarn', 'uvx', 'uv', 'bun', 'bunx']);

export function quoteWin32CmdToken(token: string): string {
  const cleaned = token.replace(/"/g, '').replace(/%/g, '^%').replace(/!/g, '^!');
  if (!/[\s&()^]/.test(cleaned)) return cleaned;
  return `"${cleaned}"`;
}

export function mcpPathIsDir(dir: string): boolean {
  try {
    return fs.statSync(dir).isDirectory();
  } catch {
    return false;
  }
}

export function mcpChildStdioReady(child: { stdin?: unknown; stdout?: unknown }): boolean {
  return Boolean(child.stdin && child.stdout);
}

/** cwd’deki sahte cmd.exe değil — System32. */
export function mcpSystemCmdExe(
  platform = process.platform,
  env: NodeJS.ProcessEnv = process.env,
): string {
  if (platform !== 'win32') return 'cmd.exe';
  const raw = String(env.SYSTEMROOT || env.WINDIR || 'C:\\Windows');
  const root = raw.split(/[\r\n]/, 1)[0]?.trim() || 'C:\\Windows';
  if (/[\0\t\v\f"'<>|&]/.test(root) || /(?:^|[\\/])\.\.(?:[\\/]|$)/.test(root)) {
    return 'C:\\Windows\\System32\\cmd.exe';
  }
  const cleaned = root.replace(/[\\/]+$/, '');
  if (!/^[a-zA-Z]:[\\/]/.test(cleaned)) return 'C:\\Windows\\System32\\cmd.exe';
  return `${cleaned}\\System32\\cmd.exe`;
}

/** cmd.exe /s /c — Node’un ekstra tırnağı /s semantiğini bozmasın. */
export function mcpWindowsVerbatimArguments(
  command: string,
  platform = process.platform,
): boolean {
  if (platform !== 'win32') return false;
  const base = path.basename(command).toLocaleLowerCase('en-US');
  return base === 'cmd.exe' || base === 'cmd';
}

export function writeMcpStdin(
  stdin: {
    write: (chunk: string) => unknown;
    writable?: boolean;
    destroyed?: boolean;
    writableEnded?: boolean;
    ended?: boolean;
  } | null | undefined,
  frame: string,
): boolean {
  if (
    !stdin ||
    stdin.writable === false ||
    stdin.destroyed === true ||
    stdin.writableEnded === true ||
    stdin.ended === true
  ) {
    return false;
  }
  try {
    stdin.write(frame);
    return true;
  } catch {
    return false;
  }
}

/** USERPROFILE yoksa HOMEDRIVE+HOMEPATH — npx göreli yazmasın. */
export function mcpWinHomePath(env: NodeJS.ProcessEnv): string {
  const drive = String(env.HOMEDRIVE ?? '').trim();
  const folder = String(env.HOMEPATH ?? '').trim();
  if (!/^[a-zA-Z]:$/.test(drive) || !folder || /[\0\t\v\f\r\n]/.test(folder)) return '';
  const pathPart = folder.startsWith('\\') || folder.startsWith('/') ? folder : `\\${folder}`;
  if (/(^|[\\/])\.\.([\\/]|$)/.test(pathPart)) return '';
  return `${drive}${pathPart}`;
}

/** npx/uvx göreli dosya yazmasın — uygulama klasörü değil ev. Yoksa cwd (ENOENT yanlış komut olmasın). */
export function mcpSpawnCwd(
  platform = process.platform,
  env: NodeJS.ProcessEnv = process.env,
  fallback = process.cwd(),
  isDir: (dir: string) => boolean = mcpPathIsDir,
): string {
  const home =
    platform === 'win32' ? env.USERPROFILE || env.HOME || mcpWinHomePath(env) : env.HOME;
  const trimmed = String(home ?? '').trim();
  if (
    !trimmed ||
    /[\0\t\v\f\r\n]/.test(trimmed) ||
    /(?:^|[\\/])\.\.(?:[\\/]|$)/.test(trimmed) ||
    !isDir(trimmed)
  ) {
    return fallback;
  }
  return trimmed;
}

export function resolveMcpSpawn(
  command: string,
  args: string[],
  platform = process.platform,
  env: NodeJS.ProcessEnv = process.env,
): { command: string; args: string[] } {
  const trimmed = command.trim();
  const base = path.basename(trimmed).toLocaleLowerCase('en-US');
  if (base === 'cmd.exe' || base === 'cmd') {
    throw new Error(hostText('cmd MCP komutu değil.', 'cmd is not an MCP command.'));
  }
  if (platform !== 'win32') return { command: trimmed, args };
  const isBatch = /\.(cmd|bat)$/i.test(base);
  const stem = base.replace(/\.(cmd|bat)$/i, '');
  if (!isBatch && !WINDOWS_BATCH_STEMS.has(stem)) return { command: trimmed, args };
  return {
    command: mcpSystemCmdExe(platform, env),
    args: ['/d', '/s', '/c', quoteWin32CmdToken(trimmed), ...args.map(quoteWin32CmdToken)],
  };
}
