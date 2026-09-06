/** Alt süreç çalıştırma yardımcıları (kabuk enjeksiyonuna kapalı). */

import { AsyncLocalStorage } from 'node:async_hooks';
import { spawn, type ChildProcess } from 'node:child_process';

import { hostText } from '../host-i18n';
import { formatHostError } from './host-error';

function isTestProcess(): boolean {
  return Boolean(process.env.VITEST || process.env.URYX_TEST_ROOT);
}

export interface RunResult {
  stdout: string;
  stderr: string;
  code: number;
}

export interface RunOptions {
  cwd?: string;
  timeoutMs?: number;
  maxBuffer?: number;
  signal?: AbortSignal;
  /** OI console chunk — compose satırını UI'ya taşımak için. */
  onChunk?: (stream: 'stdout' | 'stderr', chunk: string) => void;
}

const abortStore = new AsyncLocalStorage<AbortSignal>();
let boundAbort: AbortSignal | undefined;

/** `executeHostTool` iptal sinyalini `run()` çağrılarına bağlar (OI timeout/cancel). */
export function bindHostAbortSignal(signal?: AbortSignal): () => void {
  boundAbort = signal;
  return () => {
    if (boundAbort === signal) boundAbort = undefined;
  };
}

/** İptal sinyalini eşzamanlı araçlarda karışmadan handler'a taşır. */
export function runWithHostAbort<T>(signal: AbortSignal | undefined, work: () => Promise<T>): Promise<T> {
  if (!signal) return work();
  return abortStore.run(signal, work);
}

function effectiveSignal(options: RunOptions): AbortSignal | undefined {
  return options.signal ?? abortStore.getStore() ?? boundAbort;
}

export function currentHostAbortSignal(): AbortSignal | undefined {
  return abortStore.getStore() ?? boundAbort;
}

/** stdin kapanmazsa hung npx / cmd sarmalayıcı beklemeye devam eder. */
export function closeChildStdio(child: ChildProcess): void {
  for (const stream of [child.stdin, child.stdout, child.stderr]) {
    try {
      stream?.destroy();
    } catch {
    }
  }
}

/** Windows'ta `taskkill /T` — PowerShell/npx çocuklarını da keser (OI cancel). */
export function killProcessTree(child: ChildProcess): void {
  closeChildStdio(child);
  const pid = child.pid;
  if (process.platform === 'win32' && pid) {
    const killer = spawn('taskkill.exe', ['/PID', String(pid), '/T', '/F'], {
      windowsHide: true,
      stdio: 'ignore',
    });
    killer.unref();
    try {
      child.kill();
    } catch {
    }
    return;
  }
  try {
    child.kill('SIGKILL');
  } catch {
  }
}

/**
 * Bir çalıştırılabilir dosyayı **kabuk kullanmadan** çalıştırır.
 * Argümanlar dizi olarak geçtiği için komut enjeksiyonu mümkün değildir.
 */
export async function run(
  file: string,
  args: string[],
  options: RunOptions = {},
): Promise<RunResult> {
  const signal = effectiveSignal(options);
  if (signal?.aborted) {
    throw new Error(hostText('Komut iptal edildi.', 'The command was cancelled.'));
  }

  const timeoutMs = options.timeoutMs ?? 30_000;
  const maxBuffer = options.maxBuffer ?? 4 * 1024 * 1024;

  return new Promise<RunResult>((resolve, reject) => {
    const child = spawn(file, args, {
      cwd: options.cwd,
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    let stdout = '';
    let stderr = '';
    let settled = false;
    let timedOut = false;

    const finish = (error?: Error, result?: RunResult): void => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      signal?.removeEventListener('abort', onAbort);
      if (error) reject(error);
      else resolve(result ?? { stdout, stderr, code: 1 });
    };

    const onAbort = (): void => {
      killProcessTree(child);
      finish(new Error(hostText('Komut iptal edildi.', 'The command was cancelled.')));
    };

    const timer = setTimeout(() => {
      timedOut = true;
      killProcessTree(child);
      finish(
        new Error(
          hostText(
            `Komut zaman aşımına uğradı (${timeoutMs} ms).`,
            `The command timed out (${timeoutMs} ms).`,
          ),
        ),
      );
    }, timeoutMs);

    if (signal) {
      signal.addEventListener('abort', onAbort, { once: true });
    }

    child.stdout?.setEncoding('utf8');
    child.stderr?.setEncoding('utf8');
    child.stdout?.on('data', (chunk: string) => {
      if (stdout.length < maxBuffer) stdout += chunk;
      options.onChunk?.('stdout', chunk);
    });
    child.stderr?.on('data', (chunk: string) => {
      if (stderr.length < maxBuffer) stderr += chunk;
      options.onChunk?.('stderr', chunk);
    });

    child.on('error', (error: NodeJS.ErrnoException) => {
      if (error.code === 'ENOENT') {
        finish(
          new Error(
            hostText(
              `'${file}' bulunamadı. Programın kurulu olduğundan emin olun.`,
              `'${file}' was not found. Make sure the program is installed.`,
            ),
          ),
        );
        return;
      }
      finish(new Error(formatHostError(error)));
    });

    child.on('close', (code) => {
      if (settled) return;
      if (signal?.aborted) {
        finish(new Error(hostText('Komut iptal edildi.', 'The command was cancelled.')));
        return;
      }
      if (timedOut) {
        finish(
        new Error(
          hostText(
            `Komut zaman aşımına uğradı (${timeoutMs} ms).`,
            `The command timed out (${timeoutMs} ms).`,
          ),
        ),
      );
        return;
      }
      finish(undefined, { stdout, stderr, code: code ?? 1 });
    });
  });
}

/**
 * PowerShell betiğini `-Command` ile çalıştırır.
 * Çağıran taraf komutu `validatePowerShell` ile doğrulamış olmalıdır.
 */
export async function runPowerShell(script: string, options: RunOptions = {}): Promise<RunResult> {
  return run(
    'powershell.exe',
    ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', script],
    { timeoutMs: 45_000, ...options },
  );
}

/** Programı ayrı bir süreçte başlatır ve beklemeden döner. */
export function launchDetached(file: string, args: string[]): number | undefined {
  if (isTestProcess()) return undefined;
  const child = spawn(file, args, {
    detached: true,
    stdio: 'ignore',
    windowsHide: false,
    shell: false,
  });
  child.unref();
  return child.pid;
}

/**
 * `ms-settings:` gibi protokol URI'lerini veya kısayolları açar.
 * `explorer.exe` argümanı kabuk üzerinden geçmediği için güvenlidir.
 */
export function launchViaExplorer(target: string): void {
  if (isTestProcess()) return;
  const child = spawn('explorer.exe', [target], {
    detached: true,
    stdio: 'ignore',
    shell: false,
  });
  child.unref();
}
