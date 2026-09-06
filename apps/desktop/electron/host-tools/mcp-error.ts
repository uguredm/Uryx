/**
 * MCP süreç hatası.
 *
 * Continue: spawn+ENOENT → komut yok; timeout'ta STDERR eklenir.
 * VS Code: `error.code === 'ENOENT'` → "{command} was not found".
 */

import path from 'node:path';

import { hostT } from '../host-i18n';
import { formatHostError } from './host-error';
import { redactHostText } from './safe-url';

export function formatMcpSpawnError(error: unknown, command: string): string {
  const code =
    error && typeof error === 'object' && 'code' in error
      ? String((error as { code?: string }).code)
      : '';
  const text = error instanceof Error ? error.message : String(error ?? '');
  const fallback = hostT('mcp.commandWord').toLowerCase();
  const base = path.basename(command).replace(/[<>]/g, '') || fallback;
  const hint = hostT('mcp.firstRun');
  if (code === 'ENOENT' || /enoent/i.test(text)) {
    const stem = base.toLocaleLowerCase('en-US').replace(/\.(cmd|bat|exe)$/i, '');
    if (
      stem === 'npx' ||
      stem === 'npm' ||
      stem === 'pnpm' ||
      stem === 'pnpx' ||
      stem === 'yarn' ||
      stem === 'node' ||
      stem === 'bun' ||
      stem === 'bunx'
    ) {
      return hostT('mcp.missingNode', { base, hint });
    }
    if (
      stem === 'uvx' ||
      stem === 'uv' ||
      stem === 'python' ||
      stem === 'pythonw' ||
      stem === 'python3' ||
      stem === 'py'
    ) {
      return hostT('mcp.missingUv', { base, hint });
    }
    return hostT('mcp.missingCmd', { base });
  }
  if (code === 'EMFILE' || code === 'ENFILE' || /emfile|enfile/i.test(text)) {
    return hostT('mcp.tooManyFiles');
  }
  if (code === 'EACCES' || code === 'EPERM' || /eacces|eperm/i.test(text)) {
    return hostT('mcp.noPerm', { base });
  }
  if (code === 'E2BIG' || /e2big/i.test(text)) {
    return hostT('mcp.cmdTooLong');
  }
  if (code === 'EINVAL' || /einval/i.test(text)) {
    return hostT('mcp.einval', { base });
  }
  return formatHostError(error);
}

export function formatMcpFailure(base: string, stderr: string): string {
  const hint = redactHostText(stderr)
    .replace(/\s+/g, ' ')
    .trim()
    .slice(-240);
  const head = redactHostText(String(base ?? ''))
    .replace(/\s+/g, ' ')
    .trim();
  const firstRun =
    /zaman aşımı|timed out|timeout/i.test(head) && !hint
      ? ` ${hostT('mcp.firstRunPath', { hint: hostT('mcp.firstRun') })}`
      : '';
  if (!hint) return `${head}${firstRun}`.trim();
  return `${head} ${hint}`.slice(0, 800);
}
