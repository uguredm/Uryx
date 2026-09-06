/**
 * Preload — renderer ↔ main arasındaki **tek** güvenli köprü.
 *
 * Renderer'da `nodeIntegration` kapalı, `contextIsolation` açıktır. Bu dosya
 * `contextBridge` ile yalnızca whitelist'li kanalları açar; hiçbir Node API'si
 * (fs, child_process, path…) renderer'a sızdırılmaz.
 */

import { contextBridge, ipcRenderer } from 'electron';
import {
  IPC_EVENT_CHANNELS,
  IPC_INVOKE_CHANNELS,
  type IpcEventChannel,
  type IpcInvokeChannel,
} from '@shared/ipc';
import type { AppSettings } from '@shared/settings';

const invokeChannels = new Set<string>(IPC_INVOKE_CHANNELS);
const eventChannels = new Set<string>(IPC_EVENT_CHANNELS);

/**
 * Whitelist doğrulaması yaparak main process'i çağırır.
 * Listede olmayan kanal isteği reddedilir.
 */
async function invoke<T>(channel: IpcInvokeChannel, ...args: unknown[]): Promise<T> {
  if (!invokeChannels.has(channel)) {
    throw new Error(`İzin verilmeyen IPC kanalı: ${channel}`);
  }
  return (await ipcRenderer.invoke(channel, ...args)) as T;
}

/**
 * Main process olaylarına abone olur.
 * @returns Aboneliği kaldıran fonksiyon.
 */
function subscribe(channel: IpcEventChannel, listener: (payload: unknown) => void): () => void {
  if (!eventChannels.has(channel)) {
    throw new Error(`İzin verilmeyen olay kanalı: ${channel}`);
  }
  const wrapped = (_event: Electron.IpcRendererEvent, payload: unknown): void => listener(payload);
  ipcRenderer.on(channel, wrapped);
  return () => ipcRenderer.removeListener(channel, wrapped);
}

const bridge = {
  settings: {
    get: () => invoke<AppSettings>('settings:get'),
    set: (patch: Partial<AppSettings>) => invoke<AppSettings>('settings:set', patch),
    reset: () => invoke<AppSettings>('settings:reset'),
  },
  app: {
    info: () => invoke('app:info'),
    relaunch: () => invoke<void>('app:relaunch'),
    quit: () => invoke<void>('app:quit'),
  },
  updater: {
    getState: () => invoke('updater:getState'),
    check: () => invoke('updater:check'),
    respond: (action: 'install' | 'later') => invoke('updater:respond', action),
  },
  window: {
    minimize: () => invoke<void>('window:minimize'),
    maximize: () => invoke<boolean>('window:maximize'),
    show: () => invoke<void>('window:show'),
    hide: () => invoke<void>('window:hide'),
    isMaximized: () => invoke<boolean>('window:isMaximized'),
  },
  services: {
    status: () => invoke('services:status'),
    start: () => invoke('services:start'),
    stop: () => invoke('services:stop'),
    restart: (service?: string) => invoke('services:restart', service),
    logs: (service?: string, lines?: number) => invoke<string>('services:logs', service, lines),
    diagnose: () => invoke('services:diagnose'),
    openDocker: () => invoke('services:openDocker'),
  },
  host: {
    status: () => invoke('host:status'),
    reconnect: () => invoke('host:reconnect'),
  },
  dialog: {
    openFiles: (filters?: { name: string; extensions: string[] }[]) =>
      invoke('dialog:openFiles', filters),
    openFolder: () => invoke('dialog:openFolder'),
    saveFile: (input?: string | { defaultName?: string; content?: string }) =>
      invoke('dialog:saveFile', input),
  },
  shell: {
    openPath: (path: string) => invoke<string>('shell:openPath', path),
    showItemInFolder: (path: string) => invoke<void>('shell:showItemInFolder', path),
  },
  wake: {
    status: () => invoke('wake:status'),
    pushPcm: (samples: number[], sampleRate: number) =>
      invoke('wake:pushPcm', { samples, sampleRate }),
  },
  on: subscribe,
} as const;

contextBridge.exposeInMainWorld('uryx', bridge);

// Renderer'ın masaüstü ortamında çalıştığını anlaması için basit bir bayrak.
contextBridge.exposeInMainWorld('isUryxDesktop', true);

export type UryxPreloadBridge = typeof bridge;
