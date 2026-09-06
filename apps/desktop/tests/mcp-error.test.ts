/** Continue ENOENT + STDERR; VS Code command not found. */

import { describe, expect, it } from 'vitest';

import { formatMcpFailure, formatMcpSpawnError } from '../electron/host-tools/mcp-error';

describe('Continue / VS Code MCP process error', () => {
  it('ENOENT komut adını söyler, yol sızdırmaz', () => {
    const err = Object.assign(new Error('spawn C:\\\\secret\\\\npx ENOENT'), { code: 'ENOENT' });
    expect(formatMcpSpawnError(err, 'npx')).toMatch(/'npx' bulunamadı/);
    expect(formatMcpSpawnError(err, 'npx')).toMatch(/Node\.js/);
    expect(formatMcpSpawnError(err, 'bunx')).toMatch(/Node\.js|Bun/);
    expect(formatMcpSpawnError(err, 'npm')).toMatch(/Node\.js/);
    expect(formatMcpSpawnError(err, 'pnpm')).toMatch(/Node\.js/);
    expect(formatMcpSpawnError(err, 'yarn')).toMatch(/Node\.js/);
    expect(formatMcpSpawnError(err, 'npx')).not.toMatch(/secret/i);
    expect(formatMcpSpawnError(err, 'uvx')).toMatch(/uv kurun/);
    expect(formatMcpSpawnError(err, 'uvx')).toMatch(/40 sn/);
    expect(formatMcpSpawnError(err, 'python.exe')).toMatch(/uv kurun|Python/);
    expect(formatMcpSpawnError(err, 'python3')).toMatch(/uv kurun|Python/);
    expect(formatMcpSpawnError(err, 'pythonw.exe')).toMatch(/uv kurun|Python/);
    expect(formatMcpSpawnError(err, 'py.exe')).toMatch(/uv kurun|Python/);
    expect(formatMcpSpawnError(err, 'C:\\\\secret\\\\uvx.cmd')).toMatch(/uv kurun/);
    expect(formatMcpSpawnError(err, 'C:\\\\secret\\\\uvx.cmd')).not.toMatch(/secret/i);
    expect(formatMcpSpawnError(err, 'C:\\\\secret\\\\npx.cmd')).toMatch(/npx\.cmd/);
    expect(formatMcpSpawnError(err, 'C:\\\\secret\\\\npx.cmd')).not.toMatch(/secret/i);
  });

  it('stderr ekler, query token düşer', () => {
    const text = formatMcpFailure(
      'MCP zaman aşımı.',
      'fatal https://user:pat@ghcr.io/pkg?token=abc node missing',
    );
    expect(text).toMatch(/zaman aşımı/);
    expect(text).toMatch(/node missing/);
    expect(text).not.toMatch(/pat|token=abc/i);
  });

  it('JSON-RPC tabanı ve stderr sırları düşer', () => {
    const text = formatMcpFailure(
      'initialize failed Bearer ghp_secretleak99 Authorization: token-xyz',
      'GITHUB_PERSONAL_ACCESS_TOKEN=gho_anotherleak HF_TOKEN=hf_modelsecret99 npm_abcsecret99',
    );
    expect(text).toMatch(/initialize failed/);
    expect(text).toContain('[redacted]');
    expect(text).not.toMatch(/ghp_secretleak99|gho_anotherleak|hf_modelsecret99|npm_abcsecret99|token-xyz/i);
  });

  it('EINVAL ve EACCES komut adını söyler, yol sızdırmaz', () => {
    const einval = Object.assign(new Error('spawn C:\\\\secret\\\\npx.cmd EINVAL'), { code: 'EINVAL' });
    expect(formatMcpSpawnError(einval, 'C:\\\\secret\\\\npx.cmd')).toMatch(/npx\.cmd/);
    expect(formatMcpSpawnError(einval, 'C:\\\\secret\\\\npx.cmd')).toMatch(/EINVAL/);
    expect(formatMcpSpawnError(einval, 'C:\\\\secret\\\\npx.cmd')).not.toMatch(/secret/i);
    const eacces = Object.assign(new Error('spawn C:\\\\secret\\\\python.exe EACCES'), { code: 'EACCES' });
    expect(formatMcpSpawnError(eacces, 'C:\\\\secret\\\\python.exe')).toMatch(/python\.exe/);
    expect(formatMcpSpawnError(eacces, 'C:\\\\secret\\\\python.exe')).toMatch(/izin yok/);
    expect(formatMcpSpawnError(eacces, 'C:\\\\secret\\\\python.exe')).not.toMatch(/secret/i);
  });

  it('E2BIG komut satırı tavanını söyler', () => {
    const err = Object.assign(new Error('spawn E2BIG'), { code: 'E2BIG' });
    expect(formatMcpSpawnError(err, 'npx')).toMatch(/komut satırı çok uzun/);
  });

  it('EMFILE dosya tavanını söyler', () => {
    const err = Object.assign(new Error('spawn EMFILE'), { code: 'EMFILE' });
    expect(formatMcpSpawnError(err, 'npx')).toMatch(/açık dosya/);
    expect(formatMcpSpawnError(err, 'npx')).not.toMatch(/spawn EMFILE/);
  });

  it('boş stderr tabanı korur', () => {
    expect(formatMcpFailure('MCP zaman aşımı.', '   ')).toMatch(/zaman aşımı/);
    expect(formatMcpFailure('MCP zaman aşımı.', '   ')).toMatch(/40 sn/);
  });
});
