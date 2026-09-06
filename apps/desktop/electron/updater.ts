/** GitHub Releases üzerinden otomatik güncelleme. Önce public latest.yml, gerekirse gizli+token. */

import { app } from 'electron';
import { execFile } from 'node:child_process';
import { existsSync } from 'node:fs';
import { rm } from 'node:fs/promises';
import path from 'node:path';
import { promisify } from 'node:util';
import { autoUpdater } from 'electron-updater';
import type { UpdateState } from '@shared/ipc';

import { hostLang, hostT } from './host-i18n';
import {
  classifyUpdaterError,
  nextUpdaterFeed,
  productSafeUpdaterMessage,
  updaterStartDecision,
  type UpdaterFeed,
} from './updater-gate';
import { setQuitting } from './window';

const execFileAsync = promisify(execFile);
const CHECK_INTERVAL_MS = 4 * 60 * 60 * 1000;
const INITIAL_CHECK_DELAY_MS = 12_000;

let state: UpdateState = { phase: 'idle', version: null, percent: 0, message: null };
let notifyRenderer: ((state: UpdateState) => void) | null = null;
let downloadStarted = false;
let started = false;
let checking = false;
let currentFeed: UpdaterFeed = 'public';
let githubToken: string | null = null;

export function getUpdaterState(): UpdateState {
  return { ...state };
}

export async function respondToUpdate(action: 'install' | 'later'): Promise<UpdateState> {
  if (action === 'later') {
    setState({ phase: 'idle', version: null, percent: 0, message: null });
    return getUpdaterState();
  }

  if (state.phase === 'ready') {
    installDownloadedUpdate();
    return getUpdaterState();
  }

  if (state.phase !== 'available' || downloadStarted) return getUpdaterState();
  downloadStarted = true;
  setState({ ...state, phase: 'downloading', percent: 0, message: hostT('update.downloadingToast') });
  try {
    await autoUpdater.downloadUpdate();
  } catch (error) {
    downloadStarted = false;
    setState({
      ...state,
      phase: 'error',
      message: error instanceof Error ? error.message : hostT('update.downloadFail'),
    });
  }
  return getUpdaterState();
}

/** Ayarlar ekranından elle sürüm kontrolü. */
export async function checkForUpdatesNow(): Promise<UpdateState> {
  if (updaterStartDecision(app.isPackaged) === 'unpackaged') {
    setState({
      phase: 'error',
      version: null,
      percent: 0,
      message: hostT('update.devMode'),
    });
    return getUpdaterState();
  }

  if (!started) {
    await startAutoUpdater(notifyRenderer ?? (() => undefined));
  }

  if (!started) {
    setState({
      phase: 'error',
      version: null,
      percent: 0,
      message: hostT('update.channelFail'),
    });
    return getUpdaterState();
  }

  await runCheck({ manual: true });
  return getUpdaterState();
}

export async function startAutoUpdater(notify: (state: UpdateState) => void): Promise<void> {
  notifyRenderer = notify;
  if (updaterStartDecision(app.isPackaged) === 'unpackaged' || started) return;

  githubToken = await resolveGithubToken();
  applyGithubFeed('public');

  autoUpdater.autoDownload = false;
  autoUpdater.autoInstallOnAppQuit = true;
  autoUpdater.logger = {
    info: (...args: unknown[]) => console.info('[updater]', ...args),
    warn: (...args: unknown[]) => console.warn('[updater]', ...args),
    error: (...args: unknown[]) => console.error('[updater]', ...args),
    debug: (...args: unknown[]) => console.info('[updater]', ...args),
  };

  ;(autoUpdater as unknown as { on(event: string, listener: () => void): void }).on(
    'before-quit-for-update',
    () => {
      setQuitting(true);
    },
  );

  autoUpdater.on('checking-for-update', () => {
    checking = true;
  });

  autoUpdater.on('update-available', (info) => {
    checking = false;
    downloadStarted = false;
    setState({
      phase: 'available',
      version: info.version,
      percent: 0,
      message: hostT('update.readyToast', { version: info.version }),
    });
  });

  autoUpdater.on('update-not-available', () => {
    checking = false;
    if (state.phase === 'checking') {
      setState({
        phase: 'idle',
        version: app.getVersion(),
        percent: 0,
        message: null,
      });
    }
  });

  autoUpdater.on('download-progress', (progress) => {
    setState({
      ...state,
      phase: 'downloading',
      percent: Math.max(0, Math.min(100, progress.percent)),
      message: hostT('update.bgDownload'),
    });
  });

  autoUpdater.on('update-downloaded', (info) => {
    downloadStarted = false;
    setState({
      phase: 'ready',
      version: info.version,
      percent: 100,
      message: hostT('update.installing'),
    });
    installDownloadedUpdate();
  });

  autoUpdater.on('error', (error) => {
    checking = false;
    downloadStarted = false;
    const message = error.message;
    const next = nextUpdaterFeed({
      current: currentFeed,
      hasToken: Boolean(githubToken),
      error: message,
    });
    if (next === 'private') {
      console.info('[updater] Public latest.yml yok; gizli kanala düşülüyor.');
      applyGithubFeed('private');
      void runCheck({ manual: false });
      return;
    }
    console.warn('[updater] Güncelleme hatası:', message);
    setState({
      phase: 'error',
      version: state.version,
      percent: state.percent,
      message: humanizeUpdaterError(message),
    });
  });

  started = true;
  setTimeout(() => {
    void runCheck({ manual: false });
  }, INITIAL_CHECK_DELAY_MS);
  setInterval(() => {
    void runCheck({ manual: false });
  }, CHECK_INTERVAL_MS).unref();
}

async function runCheck(options: { manual: boolean }): Promise<void> {
  if (!started || checking) return;
  if (state.phase === 'downloading' || state.phase === 'ready') return;

  if (options.manual) {
    setState({
      phase: 'checking',
      version: null,
      percent: 0,
      message: hostT('update.checkingToast'),
    });
  }

  try {
    await clearStalePendingIfNeeded();
    await autoUpdater.checkForUpdates();
  } catch (error: unknown) {
    checking = false;
    const message = error instanceof Error ? error.message : String(error);
    const next = nextUpdaterFeed({
      current: currentFeed,
      hasToken: Boolean(githubToken),
      error: message,
    });
    if (next === 'private') {
      console.info('[updater] Public latest.yml yok; gizli kanala düşülüyor.');
      applyGithubFeed('private');
      await runCheck(options);
      return;
    }
    console.warn('[updater] Sürüm kontrolü başarısız:', message);
    if (options.manual || state.phase === 'checking') {
      setState({
        phase: 'error',
        version: null,
        percent: 0,
        message: humanizeUpdaterError(message),
      });
    }
  }
}

function installDownloadedUpdate(): void {
  setQuitting(true);
  setState({
    phase: 'ready',
    version: state.version,
    percent: 100,
    message: hostT('update.installing'),
  });
  setTimeout(() => {
    try {
      setQuitting(true);
      autoUpdater.quitAndInstall(true, true);
    } catch (error) {
      downloadStarted = false;
      setState({
        phase: 'error',
        version: state.version,
        percent: 0,
        message:
          error instanceof Error
            ? error.message
            : hostT('update.installFail'),
      });
    }
  }, 900);
}

function setState(next: UpdateState): void {
  state = next;
  notifyRenderer?.(getUpdaterState());
}

async function resolveGithubToken(): Promise<string | null> {
  const fromEnv = (process.env.GH_TOKEN || process.env.GITHUB_TOKEN || '').trim();
  if (fromEnv) return fromEnv;

  const candidates = [
    'gh.exe',
    'C:\\Program Files\\GitHub CLI\\gh.exe',
    path.join(process.env.LOCALAPPDATA ?? '', 'Programs', 'GitHub CLI', 'gh.exe'),
    path.join(process.env.ProgramFiles ?? 'C:\\Program Files', 'GitHub CLI', 'gh.exe'),
  ];

  for (const executable of candidates) {
    if (executable.includes('\\') && !existsSync(executable)) continue;
    try {
      const { stdout } = await execFileAsync(executable, ['auth', 'token'], {
        windowsHide: true,
        timeout: 10_000,
        env: process.env,
      });
      const token = stdout.trim();
      if (token) return token;
    } catch {
    }
  }
  return null;
}

/** Yarım kalmış pending installer bazen yeni indirmeyi/kurulumu bozar. */
async function clearStalePendingIfNeeded(): Promise<void> {
  const pendingDir = path.join(process.env.LOCALAPPDATA ?? '', '@uryxdesktop-updater', 'pending');
  if (!existsSync(pendingDir)) return;
  if (state.phase === 'downloading' || state.phase === 'ready') return;
  try {
    await rm(pendingDir, { recursive: true, force: true });
    console.info('[updater] Eski pending güncelleme önbelleği temizlendi.');
  } catch (error) {
    console.warn('[updater] Pending önbellek temizlenemedi:', error);
  }
}

function applyGithubFeed(mode: UpdaterFeed): void {
  currentFeed = mode;
  if (mode === 'private' && githubToken) {
    process.env.GH_TOKEN = githubToken;
    process.env.GITHUB_TOKEN = githubToken;
    autoUpdater.setFeedURL({
      provider: 'github',
      owner: 'uguredm',
      repo: 'uryx-test',
      private: true,
      releaseType: 'release',
    });
    return;
  }
  autoUpdater.setFeedURL({
    provider: 'github',
    owner: 'uguredm',
    repo: 'Uryx',
    private: false,
    releaseType: 'release',
  });
}

function humanizeUpdaterError(message: string): string {
  const kind = classifyUpdaterError(message);
  return productSafeUpdaterMessage({ kind, feed: currentFeed, language: hostLang() });
}
