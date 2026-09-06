/** Kısıtlı kabuk ve Git araçları. */

import { existsSync } from 'node:fs';
import path from 'node:path';

import { hostText } from '../host-i18n';
import { ensureDirectory, sanitizeSingleLine, validateCmd, validatePowerShell } from '../security';
import { run, runPowerShell } from './process';

const MAX_OUTPUT_CHARS = 12_000;

/** Çıktıyı makul boyuta indirir. */
function trimOutput(value: string): { text: string; truncated: boolean } {
  const text = value.trim();
  return text.length > MAX_OUTPUT_CHARS
    ? { text: text.slice(0, MAX_OUTPUT_CHARS), truncated: true }
    : { text, truncated: false };
}

/** `run_powershell` aracı — allowlist doğrulaması `security.ts` içinde. */
export async function runPowerShellTool(args: Record<string, unknown>): Promise<
  Record<string, unknown>
> {
  const command = validatePowerShell(String(args.command ?? ''));
  const rawCwd = sanitizeSingleLine(args.cwd ?? '', 1000);
  const cwd = rawCwd ? ensureDirectory(rawCwd) : undefined;

  const result = await runPowerShell(command, { cwd, timeoutMs: 45_000 });
  const stdout = trimOutput(result.stdout);
  const stderr = trimOutput(result.stderr);

  return {
    command,
    exit_code: result.code,
    stdout: stdout.text,
    stderr: stderr.text,
    truncated: stdout.truncated || stderr.truncated,
  };
}

/** `run_cmd` aracı. */
export async function runCmdTool(args: Record<string, unknown>): Promise<Record<string, unknown>> {
  const { command, args: argv } = validateCmd(String(args.command ?? ''));
  const rawCwd = sanitizeSingleLine(args.cwd ?? '', 1000);
  const cwd = rawCwd ? ensureDirectory(rawCwd) : undefined;

  const builtins = new Set(['dir', 'echo', 'ver']);
  const result = builtins.has(command)
    ? await run('cmd.exe', ['/d', '/c', command, ...argv], { cwd, timeoutMs: 30_000 })
    : await run(`${command}.exe`, argv, { cwd, timeoutMs: 30_000 });

  const stdout = trimOutput(result.stdout);
  const stderr = trimOutput(result.stderr);

  return {
    command: [command, ...argv].join(' '),
    exit_code: result.code,
    stdout: stdout.text,
    stderr: stderr.text,
    truncated: stdout.truncated || stderr.truncated,
  };
}

/** Klasörün bir Git deposu olduğunu doğrular. */
function ensureGitRepo(rawPath: string): string {
  const resolved = ensureDirectory(rawPath);
  if (!existsSync(path.join(resolved, '.git'))) {
    throw new Error(
      hostText(
        `'${rawPath}' bir Git deposu değil (.git klasörü yok).`,
        `'${rawPath}' is not a Git repository (no .git folder).`,
      ),
    );
  }
  return resolved;
}

/** `git_status` aracı. */
export async function gitStatus(args: Record<string, unknown>): Promise<Record<string, unknown>> {
  const cwd = ensureGitRepo(sanitizeSingleLine(args.path, 1000));

  const [status, branch] = await Promise.all([
    run('git', ['status', '--porcelain=v1', '--branch'], { cwd, timeoutMs: 20_000 }),
    run('git', ['rev-parse', '--abbrev-ref', 'HEAD'], { cwd, timeoutMs: 10_000 }),
  ]);

  if (status.code !== 0) {
    throw new Error(
      hostText(
        `git status başarısız: ${status.stderr.trim().slice(0, 300)}`,
        `git status failed: ${status.stderr.trim().slice(0, 300)}`,
      ),
    );
  }

  const lines = status.stdout.trim().split('\n').filter(Boolean);
  const files = lines
    .filter((l) => !l.startsWith('##'))
    .map((l) => ({ state: l.slice(0, 2).trim(), file: l.slice(3) }));

  return {
    path: cwd,
    branch: branch.stdout.trim() || hostText('bilinmiyor', 'unknown'),
    clean: files.length === 0,
    changed_count: files.length,
    files: files.slice(0, 100),
  };
}

/** `git_commit` aracı. */
export async function gitCommit(args: Record<string, unknown>): Promise<Record<string, unknown>> {
  const cwd = ensureGitRepo(sanitizeSingleLine(args.path, 1000));
  const message = sanitizeSingleLine(args.message, 300);
  if (!message) throw new Error(hostText('Commit mesajı gerekli.', 'A commit message is required.'));

  const staged = await run('git', ['add', '-A'], { cwd, timeoutMs: 30_000 });
  if (staged.code !== 0) {
    throw new Error(
      hostText(
        `git add başarısız: ${staged.stderr.trim().slice(0, 300)}`,
        `git add failed: ${staged.stderr.trim().slice(0, 300)}`,
      ),
    );
  }

  const result = await run('git', ['commit', '-m', message], { cwd, timeoutMs: 30_000 });
  if (result.code !== 0) {
    const output = `${result.stdout}${result.stderr}`.trim();
    if (/nothing to commit/i.test(output)) {
      return {
        committed: false,
        detail: hostText('Commit edilecek değişiklik yok.', 'Nothing to commit.'),
      };
    }
    throw new Error(
      hostText(`git commit başarısız: ${output.slice(0, 400)}`, `git commit failed: ${output.slice(0, 400)}`),
    );
  }

  const hash = await run('git', ['rev-parse', '--short', 'HEAD'], { cwd, timeoutMs: 10_000 });
  return { committed: true, message, commit: hash.stdout.trim(), path: cwd };
}

/** `git_push` aracı. */
export async function gitPush(args: Record<string, unknown>): Promise<Record<string, unknown>> {
  const cwd = ensureGitRepo(sanitizeSingleLine(args.path, 1000));
  const remote = sanitizeSingleLine(args.remote ?? 'origin', 60) || 'origin';
  let branch = sanitizeSingleLine(args.branch ?? '', 120);

  if (!/^[\w.\-/]+$/.test(remote)) {
    throw new Error(hostText('Geçersiz remote adı.', 'Invalid remote name.'));
  }
  if (branch && !/^[\w.\-/]+$/.test(branch)) {
    throw new Error(hostText('Geçersiz dal adı.', 'Invalid branch name.'));
  }

  if (!branch) {
    const current = await run('git', ['rev-parse', '--abbrev-ref', 'HEAD'], { cwd });
    branch = current.stdout.trim();
  }
  if (!branch || branch === 'HEAD') {
    throw new Error(hostText('Aktif dal belirlenemedi.', 'Could not determine the active branch.'));
  }

  const result = await run('git', ['push', remote, branch], { cwd, timeoutMs: 120_000 });
  const output = `${result.stdout}${result.stderr}`.trim();
  if (result.code !== 0) {
    throw new Error(
      hostText(`git push başarısız: ${output.slice(0, 500)}`, `git push failed: ${output.slice(0, 500)}`),
    );
  }
  return { pushed: true, remote, branch, output: output.slice(0, 1000) };
}
