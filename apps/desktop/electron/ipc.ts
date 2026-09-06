/**
 * IPC işleyicileri.
 *
 * Güvenlik kuralları:
 *  - Yalnızca `IPC_INVOKE_CHANNELS` listesindeki kanallar kaydedilir.
 *  - Her handler girdiyi doğrular; renderer'dan gelen veriye güvenilmez.
 *  - Dosya sistemi ve kabuk işlemleri asla renderer'da çalışmaz.
 */

import { app, BrowserWindow, dialog, ipcMain, shell } from 'electron';
import { writeFile } from 'node:fs/promises';
import { IPC_INVOKE_CHANNELS, type IpcInvokeChannel } from '@shared/ipc';
import type { AppSettings } from '@shared/settings';

import type { HostBridgeClient } from './host-bridge';
import { hostLang, hostT } from './host-i18n';
import { ensureMarkdownPath, parseSaveTextPayload } from './save-export';
import { isPathAllowed } from './security';
import { recentHostToolAudit, requestHostCapabilitiesRefresh } from './host-tools';
import {
  diagnoseServices,
  getServiceLogs,
  getServicesStatus,
  openDockerDesktop,
  recreateLlmService,
  restartServices,
  setServicesProgressSink,
  startServices,
  stopServices,
  findRepoRoot,
} from './services';
import { applyLlmComposeEnv, listGgufFiles, presetFromSettings, resolveModelsDir } from './models-dir';
import { notifyDesktop } from './windows-desktop';
import { updateTrayStatus } from './tray';
import { mcpSettingsNeedCapabilityRefresh, onMcpSettingsChanged } from './host-tools/mcp';
import { getSettings, resetSettings, settingsPath, updateSettings } from './store';
import { getUpdaterState, respondToUpdate, checkForUpdatesNow } from './updater';
import { getMainWindow, setQuitting } from './window';
import { wakePushPcmForIpc, wakeStatusForIpc } from './wake-onnx';

/** Kaydedilen kanalların takibi (çift kayıt koruması). */
const registered = new Set<IpcInvokeChannel>();

/**
 * Whitelist doğrulaması yaparak bir invoke handler kaydeder.
 * Listede olmayan bir kanal kaydedilmeye çalışılırsa hata fırlatılır.
 */
function handle(
  channel: IpcInvokeChannel,
  listener: (...args: unknown[]) => Promise<unknown> | unknown,
): void {
  if (!IPC_INVOKE_CHANNELS.includes(channel)) {
    throw new Error(hostT('ipc.channel', { channel }));
  }
  if (registered.has(channel)) return;
  registered.add(channel);

  ipcMain.handle(channel, async (_event, ...args) => {
    try {
      return await listener(...args);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      throw new Error(message.slice(0, 500));
    }
  });
}

export interface IpcContext {
  hostBridge: HostBridgeClient;
  onSettingsChanged: (settings: AppSettings) => void;
}

async function refreshHostChrome(): Promise<void> {
  try {
    const status = await getServicesStatus();
    updateTrayStatus({
      dockerAvailable: status.dockerAvailable,
      apiReachable: status.apiReachable,
      engineState: status.engineState,
    });
  } catch {
  }
}

/** Tüm IPC işleyicilerini kaydeder. */
export function registerIpcHandlers(context: IpcContext): void {
  setServicesProgressSink((payload) => broadcast('services:progress', payload));

  handle('settings:get', () => getSettings());

  handle('settings:set', (patch) => {
    if (typeof patch !== 'object' || patch === null || Array.isArray(patch)) {
      throw new Error(hostT('ipc.settingsObject'));
    }
    const prev = getSettings();
    const next = updateSettings(patch as Partial<AppSettings>);
    onMcpSettingsChanged(prev, next);
    if (mcpSettingsNeedCapabilityRefresh(prev, next)) {
      requestHostCapabilitiesRefresh();
    }
    context.onSettingsChanged(next);
    const root = findRepoRoot();
    if (root) {
      applyLlmComposeEnv(root, presetFromSettings(next.modelName, next.llmPreset), next.modelName);
    }
    if (prev.llmPreset !== next.llmPreset || prev.modelName !== next.modelName) {
      void recreateLlmService();
    }
    return next;
  });

  handle('settings:reset', () => {
    const prev = getSettings();
    const next = resetSettings();
    onMcpSettingsChanged(prev, next);
    if (mcpSettingsNeedCapabilityRefresh(prev, next)) {
      requestHostCapabilitiesRefresh();
    }
    context.onSettingsChanged(next);
    return next;
  });

  handle('app:info', () => ({
    version: app.getVersion(),
    electronVersion: process.versions.electron,
    chromeVersion: process.versions.chrome,
    nodeVersion: process.versions.node,
    platform: process.platform,
    arch: process.arch,
    isPackaged: app.isPackaged,
    userDataPath: settingsPath(),
    repoRoot: findRepoRoot(),
    modelsDir: resolveModelsDir(),
    ggufFiles: listGgufFiles(),
  }));

  handle('app:relaunch', () => {
    setQuitting(true);
    app.relaunch();
    app.exit(0);
  });

  handle('app:quit', () => {
    setQuitting(true);
    app.quit();
  });

  handle('updater:getState', () => getUpdaterState());
  handle('updater:check', () => checkForUpdatesNow());
  handle('updater:respond', (action) => {
    if (action !== 'install' && action !== 'later') {
      throw new Error(hostT('ipc.updateDecision'));
    }
    return respondToUpdate(action);
  });

  handle('window:minimize', () => {
    getMainWindow()?.minimize();
  });

  handle('window:maximize', () => {
    const window = getMainWindow();
    if (!window) return false;
    if (window.isMaximized()) {
      window.unmaximize();
      return false;
    }
    window.maximize();
    return true;
  });

  handle('window:show', () => {
    const window = getMainWindow();
    if (!window) return;
    if (window.isMinimized()) window.restore();
    window.show();
    window.focus();
  });

  handle('window:hide', () => {
    getMainWindow()?.hide();
  });

  handle('window:isMaximized', () => getMainWindow()?.isMaximized() ?? false);

  handle('services:status', () => getServicesStatus());
  handle('services:start', async () => {
    const result = await startServices();
    if (!result.ok) notifyDesktop('Uryx', result.message);
    void refreshHostChrome();
    return result;
  });
  handle('services:stop', () => stopServices());
  handle('services:restart', async (service) => {
    const result = await restartServices(typeof service === 'string' ? service : undefined);
    if (!result.ok) notifyDesktop('Uryx', result.message);
    void refreshHostChrome();
    return result;
  });
  handle('services:logs', (service, lines) =>
    getServiceLogs(typeof service === 'string' ? service : '', Number(lines) || 200),
  );
  handle('services:diagnose', () => diagnoseServices());
  handle('services:openDocker', async () => {
    const result = await openDockerDesktop();
    if (!result.ok) notifyDesktop('Uryx', result.message);
    void refreshHostChrome();
    return result;
  });

  handle('host:status', () => ({
    ...context.hostBridge.state,
    recentTools: recentHostToolAudit(),
  }));
  handle('host:reconnect', () => {
    context.hostBridge.reconnect();
    return {
      ...context.hostBridge.state,
      recentTools: recentHostToolAudit(),
    };
  });

  handle('dialog:openFiles', async (filters) => {
    const window = getMainWindow();
    const safeFilters = Array.isArray(filters)
      ? (filters as { name: string; extensions: string[] }[])
          .filter((f) => f && typeof f.name === 'string' && Array.isArray(f.extensions))
          .slice(0, 10)
      : undefined;

    const result = window
      ? await dialog.showOpenDialog(window, {
          properties: ['openFile', 'multiSelections'],
          filters: safeFilters,
        })
      : await dialog.showOpenDialog({ properties: ['openFile', 'multiSelections'] });

    return { canceled: result.canceled, filePaths: result.filePaths };
  });

  handle('dialog:openFolder', async () => {
    const window = getMainWindow();
    const result = window
      ? await dialog.showOpenDialog(window, { properties: ['openDirectory'] })
      : await dialog.showOpenDialog({ properties: ['openDirectory'] });
    return { canceled: result.canceled, filePaths: result.filePaths };
  });

  handle('dialog:saveFile', async (payload) => {
    const { defaultName, content } = parseSaveTextPayload(payload, hostLang());
    const window = getMainWindow();
    const options = {
      title: hostT('dialog.saveChat'),
      defaultPath: defaultName,
      filters: [{ name: 'Markdown', extensions: ['md'] }],
    };
    const result = window
      ? await dialog.showSaveDialog(window, options)
      : await dialog.showSaveDialog(options);
    if (result.canceled || !result.filePath) {
      return { canceled: true, filePaths: [] };
    }
    const target = ensureMarkdownPath(result.filePath, hostLang());
    if (!isPathAllowed(target)) {
      throw new Error(hostT('ipc.saveFolder'));
    }
    if (content) {
      await writeFile(target, content, 'utf8');
      shell.showItemInFolder(target);
    }
    return { canceled: false, filePaths: [target] };
  });

  handle('shell:openPath', async (target) => {
    const value = String(target ?? '');
    if (!isPathAllowed(value)) {
      throw new Error(hostT('ipc.pathDenied'));
    }
    return shell.openPath(value);
  });

  handle('shell:showItemInFolder', (target) => {
    const value = String(target ?? '');
    if (!isPathAllowed(value)) {
      throw new Error(hostT('ipc.pathDenied'));
    }
    shell.showItemInFolder(value);
  });

  handle('audio:listInputDevices', () => ({
    supported: true,
    note: hostT('ipc.audioNote'),
  }));

  handle('wake:status', () => wakeStatusForIpc());

  handle('wake:pushPcm', (payload) => wakePushPcmForIpc(payload));
}

/** Kayıtlı tüm IPC işleyicilerini kaldırır (uygulama kapanışı). */
export function unregisterIpcHandlers(): void {
  setServicesProgressSink(null);
  for (const channel of registered) {
    ipcMain.removeHandler(channel);
  }
  registered.clear();
}

/** Aktif tüm pencerelere olay yayınlar. */
export function broadcast(channel: string, payload?: unknown): void {
  for (const window of BrowserWindow.getAllWindows()) {
    if (!window.isDestroyed()) window.webContents.send(channel, payload);
  }
}
