/**
 * Electron main process giriş noktası.
 *
 * Sorumlulukları:
 *  - Tek örnek (single instance) kilidi
 *  - Ana pencere + sistem tepsisi
 *  - Global kısayol (varsayılan: Ctrl+Shift+J) ve push-to-talk
 *  - Windows ile otomatik başlatma
 *  - Backend host köprüsü (`/ws/host`) — host araçları ve sistem metrikleri
 *  - Güvenli IPC katmanı
 */

import { app, globalShortcut, net, powerMonitor, protocol } from 'electron';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

import { HostBridgeClient } from './host-bridge';
import { hostT } from './host-i18n';
import { broadcast, registerIpcHandlers, unregisterIpcHandlers } from './ipc';
import { ensureFile, setExtraAllowedRoots } from './security';
import { shutdownMcpRuntime } from './host-tools/mcp';
import { getSettings } from './store';
import {
  diagnoseServices,
  getServicesStatus,
  openDockerDesktop,
  startServices,
  syncPackagedServices,
  waitForApiHealth,
} from './services';
import { createTray, destroyTray, refreshTrayChrome, setTrayActions, updateTrayStatus } from './tray';
import { startAutoUpdater } from './updater';
import {
  createMainWindow,
  getMainWindow,
  sendToRenderer,
  setQuitting,
  showMainWindow,
  toggleMainWindow,
} from './window';
import {
  argvRequestsNewChat,
  handleDesktopArgv,
  installJumpList,
  notifyDesktop,
} from './windows-desktop';
import type { AppSettings } from '@shared/settings';
import {
  EXTRA_HOST_HOTKEYS,
  pushToTalkAccelerator,
  sanitizeAccelerator,
} from './hotkeys';

const hostBridge = new HostBridgeClient();
let trayHealthTimer: ReturnType<typeof setInterval> | null = null;

/** Docker Desktop tepsisi gibi motor/API durumunu periyodik yoklar. */
function startTrayHealthLoop(): void {
  if (trayHealthTimer) return;
  const tick = async (): Promise<void> => {
    try {
      const status = await getServicesStatus();
      updateTrayStatus({
        dockerAvailable: status.dockerAvailable,
        apiReachable: status.apiReachable,
        engineState: status.engineState,
      });
      if (status.apiReachable && !hostBridge.state.connected) {
        hostBridge.ensureConnected();
      }
    } catch {
    }
  };
  void tick();
  trayHealthTimer = setInterval(() => void tick(), 30_000);
}

const MEDIA_EXTENSIONS = new Set([
  '.png',
  '.jpg',
  '.jpeg',
  '.webp',
  '.gif',
  '.bmp',
  '.mp4',
  '.webm',
  '.mov',
  '.m4v',
]);

protocol.registerSchemesAsPrivileged([
  { scheme: 'uryx-media', privileges: { secure: true, supportFetchAPI: true, stream: true } },
]);

/** Kayıtlı global kısayollar (yeniden kayıt için izlenir). */
let registeredShortcut: string | null = null;
let registeredPushToTalk: string | null = null;
const registeredExtras = new Set<string>();

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', (_event, argv) => handleDesktopArgv(argv));
  void bootstrap();
}

/** Uygulamayı başlatır. */
async function bootstrap(): Promise<void> {
  app.commandLine.appendSwitch('disable-features', 'OutOfBlinkCors');
  app.setAppUserModelId('com.uryx.desktop');

  await app.whenReady();

  protocol.handle('uryx-media', (request) => {
    try {
      const target = new URL(request.url).searchParams.get('path') ?? '';
      const file = ensureFile(target);
      if (!MEDIA_EXTENSIONS.has(path.extname(file).toLowerCase())) {
        return new Response(hostT('media.unsupported'), { status: 415 });
      }
      return net.fetch(pathToFileURL(file).toString());
    } catch {
      return new Response(hostT('media.denied'), { status: 403 });
    }
  });

  const settings = getSettings();
  applySettings(settings, { initial: true });

  registerIpcHandlers({
    hostBridge,
    onSettingsChanged: (next) => applySettings(next, { initial: false }),
  });

  createMainWindow();
  installJumpList();
  setTrayActions({
    startServices: () => {
      void startServices().then((result) => {
        if (!result.ok) {
          broadcast('app:error', { message: result.message });
          notifyDesktop('Uryx', result.message);
        }
      });
    },
    openDocker: () => {
      void openDockerDesktop().then((result) => {
        if (!result.ok) {
          broadcast('app:error', { message: result.message });
          notifyDesktop('Uryx', result.message);
        }
      });
    },
    diagnose: () => {
      showMainWindow();
      sendToRenderer('tray:openSystem');
      void diagnoseServices().then((status) => {
        updateTrayStatus({
          dockerAvailable: status.dockerAvailable,
          apiReachable: status.apiReachable,
          engineState: status.engineState,
        });
        const hint =
          status.hints[0] ?? (status.apiReachable ? hostT('notify.apiReady') : hostT('notify.apiDown'));
        notifyDesktop(hostT('notify.diagTitle'), hint);
      });
    },
  });
  createTray();
  startTrayHealthLoop();

  void startAutoUpdater((state) => broadcast('updater:state', state));

  let hostWasConnected = false;
  hostBridge.on('connection', (state) => {
    broadcast('host:connectionChanged', state);
    updateTrayStatus({ hostConnected: state.connected });
    if (hostWasConnected && !state.connected) {
      notifyDesktop('Uryx', hostT('notify.bridgeDropped'));
      getMainWindow()?.flashFrame(true);
    }
    hostWasConnected = state.connected;
  });
  bindHostPowerEvents();
  void prepareServicesAndHostBridge(settings);

  if (argvRequestsNewChat()) {
    setTimeout(() => sendToRenderer('tray:newChat'), 800);
  }

  app.on('activate', () => showMainWindow());
}

/** Paket güncellemesinde API hazır olmadan host köprüsünün yanlışlıkla kapalı görünmesini önler. */
async function prepareServicesAndHostBridge(settings: AppSettings): Promise<void> {
  const result = await syncPackagedServices(app.getVersion());
  if (result && !result.ok) broadcast('app:error', { message: result.message });

  await waitForApiHealth(settings.backendUrl, result?.ok ? 45 : 8);
  try {
    const status = await getServicesStatus();
    updateTrayStatus({
      dockerAvailable: status.dockerAvailable,
      apiReachable: status.apiReachable,
      engineState: status.engineState,
    });
  } catch {
  }
  hostBridge.start();
}

/** VS Code `onDidResumeOS` — uyku sonrası `/ws/host` hemen bağlanır. */
function bindHostPowerEvents(): void {
  if (process.env.VITEST) return;
  powerMonitor.on('suspend', () => hostBridge.handlePowerSuspend());
  powerMonitor.on('resume', () => {
    hostBridge.handlePowerResume();
  });
}

/** Ayar değişikliklerini uygular. */
function applySettings(settings: AppSettings, { initial }: { initial: boolean }): void {
  hostBridge.configure(settings.backendUrl, settings.localToken, app.getVersion());
  if (!initial) hostBridge.reannounceCapabilities();

  if (process.platform === 'win32') {
    app.setLoginItemSettings({
      openAtLogin: settings.launchOnStartup,
      openAsHidden: settings.minimizeToTray,
      args: ['--hidden'],
    });
  }

  setExtraAllowedRoots(process.env.URYX_REPO_ROOT ? [process.env.URYX_REPO_ROOT] : []);

  registerShortcuts(settings);

  refreshTrayChrome();
  installJumpList();

  if (initial && process.argv.includes('--hidden')) {
    setTimeout(() => {
      const shouldHide = getSettings().minimizeToTray;
      if (shouldHide) sendToRenderer('app:startedHidden');
    }, 500);
  }
}

function runExtraHotkey(action: (typeof EXTRA_HOST_HOTKEYS)[number]['action']): void {
  showMainWindow();
  if (action === 'newChat') sendToRenderer('tray:newChat');
  if (action === 'openSystem') sendToRenderer('tray:openSystem');
}

/** Global kısayolları (yeniden) kaydeder. Win/Super asla kayıt olmaz. */
function registerShortcuts(settings: AppSettings): void {
  const windowAccel = sanitizeAccelerator(settings.globalShortcut);

  if (registeredShortcut && registeredShortcut !== windowAccel) {
    globalShortcut.unregister(registeredShortcut);
    registeredShortcut = null;
  }

  if (windowAccel && registeredShortcut !== windowAccel) {
    try {
      const ok = globalShortcut.register(windowAccel, () => toggleMainWindow());
      registeredShortcut = ok ? windowAccel : null;
      if (!ok) {
        broadcast('app:error', {
          message: hostT('shortcut.registerFail', { accel: windowAccel }),
        });
      }
    } catch (error) {
      broadcast('app:error', {
        message: hostT('shortcut.error', {
          detail: error instanceof Error ? error.message : String(error),
        }),
      });
    }
  }

  const pttAccelerator = pushToTalkAccelerator(settings.pushToTalkKey);
  if (registeredPushToTalk && registeredPushToTalk !== pttAccelerator) {
    globalShortcut.unregister(registeredPushToTalk);
    registeredPushToTalk = null;
  }
  if (pttAccelerator && registeredPushToTalk !== pttAccelerator) {
    try {
      const ok = globalShortcut.register(pttAccelerator, () => {
        showMainWindow();
        sendToRenderer('shortcut:pushToTalk');
      });
      registeredPushToTalk = ok ? pttAccelerator : null;
    } catch {
      registeredPushToTalk = null;
    }
  }

  for (const extra of registeredExtras) {
    globalShortcut.unregister(extra);
  }
  registeredExtras.clear();
  for (const item of EXTRA_HOST_HOTKEYS) {
    const accel = sanitizeAccelerator(item.accelerator);
    if (!accel || accel === windowAccel || accel === pttAccelerator) continue;
    try {
      if (globalShortcut.register(accel, () => runExtraHotkey(item.action))) {
        registeredExtras.add(accel);
      }
    } catch {
    }
  }
}

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin' && !getSettings().closeToTray) {
    setQuitting(true);
    app.quit();
  }
});

app.on('before-quit', () => {
  setQuitting(true);
  shutdownMcpRuntime();
});

app.on('will-quit', () => {
  shutdownMcpRuntime();
  globalShortcut.unregisterAll();
  hostBridge.stop();
  unregisterIpcHandlers();
  if (trayHealthTimer) {
    clearInterval(trayHealthTimer);
    trayHealthTimer = null;
  }
  destroyTray();
});

process.on('uncaughtException', (error) => {
  console.error('[main] uncaughtException', error);
  broadcast('app:error', { message: hostT('app.unexpected', { detail: error.message }) });
});

process.on('unhandledRejection', (reason) => {
  console.error('[main] unhandledRejection', reason);
});
