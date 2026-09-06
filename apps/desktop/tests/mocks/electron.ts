/**
 * Electron API'sinin test sahtesi.
 *
 * `vitest.config.ts` içindeki alias sayesinde `import ... from 'electron'`
 * çağrıları bu modüle yönlendirilir.
 */

import { mkdirSync } from 'node:fs';
import { join } from 'node:path';

const root = process.env.URYX_TEST_ROOT ?? join(process.cwd(), '.uryx-test');

/** Test için sabit klasör yolları. */
const PATHS: Record<string, string> = {
  documents: join(root, 'Documents'),
  desktop: join(root, 'Desktop'),
  downloads: join(root, 'Downloads'),
  pictures: join(root, 'Pictures'),
  userData: join(root, 'UserData'),
  appData: join(root, 'AppData'),
  exe: join(root, 'uryx.exe'),
};

for (const path of Object.values(PATHS)) {
  if (!path.endsWith('.exe')) mkdirSync(path, { recursive: true });
}

export const app = {
  getPath: (name: string): string => PATHS[name] ?? root,
  getAppPath: (): string => root,
  getVersion: (): string => '0.1.0-test',
  isPackaged: false,
  setAppUserModelId: (): void => undefined,
  setUserTasks: (): void => undefined,
  setLoginItemSettings: (): void => undefined,
  whenReady: async (): Promise<void> => undefined,
  on: (): void => undefined,
  quit: (): void => undefined,
  relaunch: (): void => undefined,
  exit: (): void => undefined,
  requestSingleInstanceLock: (): boolean => true,
  commandLine: { appendSwitch: (): void => undefined },
};

export const shell = {
  openPath: async (): Promise<string> => '',
  showItemInFolder: (): void => undefined,
  openExternal: async (): Promise<void> => undefined,
  trashItem: async (): Promise<void> => undefined,
};

export const clipboard = {
  _value: '',
  readText(): string {
    return this._value;
  },
  writeText(value: string): void {
    this._value = value;
  },
};

export const ipcMain = {
  handlers: new Map<string, unknown>(),
  handle(channel: string, listener: unknown): void {
    this.handlers.set(channel, listener);
  },
  removeHandler(channel: string): void {
    this.handlers.delete(channel);
  },
};

export const ipcRenderer = {
  invoke: async (): Promise<unknown> => undefined,
  on: (): void => undefined,
  removeListener: (): void => undefined,
};

export const contextBridge = {
  exposed: new Map<string, unknown>(),
  exposeInMainWorld(key: string, value: unknown): void {
    this.exposed.set(key, value);
  },
};

export const dialog = {
  showOpenDialog: async (): Promise<{ canceled: boolean; filePaths: string[] }> => ({
    canceled: true,
    filePaths: [],
  }),
  showSaveDialog: async (): Promise<{ canceled: boolean; filePath?: string }> => ({
    canceled: true,
  }),
};

export const BrowserWindow = {
  getAllWindows: (): unknown[] => [],
};

export const globalShortcut = {
  register: (): boolean => true,
  unregister: (): void => undefined,
  unregisterAll: (): void => undefined,
};

export const screen = {
  getPrimaryDisplay: () => ({ id: 1, size: { width: 1920, height: 1080 }, scaleFactor: 1 }),
  getAllDisplays: () => [{ id: 1, size: { width: 1920, height: 1080 }, scaleFactor: 1 }],
};

export const powerMonitor = {
  getSystemIdleTime: (): number => 0,
  isOnBatteryPower: (): boolean => false,
  on: (): void => undefined,
};

export const desktopCapturer = {
  getSources: async (): Promise<unknown[]> => [],
};

export const nativeImage = {
  createFromPath: () => ({ isEmpty: () => true, resize: () => ({}) }),
  createFromDataURL: () => ({ isEmpty: () => false, resize: () => ({}) }),
};

export const Tray = class {
  setToolTip(): void {
    return undefined;
  }
  setContextMenu(): void {
    return undefined;
  }
  on(): void {
    return undefined;
  }
  destroy(): void {
    return undefined;
  }
};
export const Menu = { buildFromTemplate: (): unknown => ({}) };

export const net = {
  fetch: async (): Promise<{ ok: boolean }> => ({ ok: false }),
};

export class Notification {
  static isSupported(): boolean {
    return false;
  }
  on(): this {
    return this;
  }
  show(): void {
    return undefined;
  }
}

export default {
  app,
  shell,
  clipboard,
  ipcMain,
  ipcRenderer,
  contextBridge,
  dialog,
  BrowserWindow,
  globalShortcut,
  screen,
  powerMonitor,
  desktopCapturer,
  nativeImage,
  Tray,
  Menu,
  net,
  Notification,
};
