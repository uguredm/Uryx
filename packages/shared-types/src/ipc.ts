/**
 * Electron IPC sözleşmesi.
 *
 * Renderer yalnızca `preload` üzerinden açılan bu kanallara erişebilir.
 * Kanal adları whitelist'tir; listede olmayan hiçbir kanal çağrılamaz.
 */

import type { AppSettings } from './settings';

/** Renderer → Main (invoke) kanalları. */
export const IPC_INVOKE_CHANNELS = [
  'settings:get',
  'settings:set',
  'settings:reset',
  'app:info',
  'app:relaunch',
  'app:quit',
  'updater:getState',
  'updater:check',
  'updater:respond',
  'window:minimize',
  'window:maximize',
  'window:show',
  'window:hide',
  'window:isMaximized',
  'services:status',
  'services:start',
  'services:stop',
  'services:restart',
  'services:logs',
  'services:diagnose',
  'services:openDocker',
  'host:status',
  'host:reconnect',
  'dialog:openFiles',
  'dialog:openFolder',
  'dialog:saveFile',
  'shell:openPath',
  'shell:showItemInFolder',
  'audio:listInputDevices',
  'wake:status',
  'wake:pushPcm',
] as const;

/** Main → Renderer (event) kanalları. */
export const IPC_EVENT_CHANNELS = [
  'shortcut:toggleWindow',
  'shortcut:pushToTalk',
  'host:connectionChanged',
  'services:progress',
  'tray:newChat',
  'tray:openSettings',
  'tray:openSystem',
  'app:error',
  'updater:state',
] as const;

export type IpcInvokeChannel = (typeof IPC_INVOKE_CHANNELS)[number];
export type IpcEventChannel = (typeof IPC_EVENT_CHANNELS)[number];

export interface AppInfo {
  version: string;
  electronVersion: string;
  chromeVersion: string;
  nodeVersion: string;
  platform: string;
  arch: string;
  isPackaged: boolean;
  userDataPath: string;
  repoRoot: string | null;
  modelsDir: string;
  ggufFiles: string[];
}

export interface DockerServiceInfo {
  name: string;
  state: string;
  health: string | null;
  image: string;
}

export interface ServicesStatus {
  dockerAvailable: boolean;
  composeAvailable: boolean;
  gpuAvailable: boolean;
  gpuName: string | null;
  services: DockerServiceInfo[];
  error: string | null;
  repoRoot?: string | null;
  apiReachable?: boolean;
  apiLatencyMs?: number | null;
  dockerDesktopInstalled?: boolean;
  engineState?: 'up' | 'starting' | 'down';
  dockerCliAvailable?: boolean;
  hostDockerAccess?: 'ok' | 'cli_only' | 'missing';
  dockerContext?: string;
  dockerContextKind?: 'default' | 'podman' | 'remote' | 'custom';
  dockerContextRedirected?: boolean;
  dockerHostSet?: boolean;
  hints?: string[];
}

export interface ServicesProgress {
  phase: string;
  message: string;
}

export interface HostToolAuditEntry {
  name: string;
  success: boolean;
  ms: number;
  at: number;
  error: string | null;
  policy?: 'safe' | 'unsafe';
}

export interface ServicesActionResult {
  ok: boolean;
  message: string;
  output?: string;
}

export interface HostConnectionState {
  connected: boolean;
  url: string;
  lastError: string | null;
  reconnectAttempts: number;
  recentTools?: HostToolAuditEntry[];
  inFlight?: number;
  capabilitiesAnnounced?: boolean;
}

export interface AudioInputDevice {
  deviceId: string;
  label: string;
}

export interface OpenFilesResult {
  canceled: boolean;
  filePaths: string[];
}

export type UpdatePhase =
  | 'idle'
  | 'checking'
  | 'available'
  | 'downloading'
  | 'ready'
  | 'error';

export interface UpdateState {
  phase: UpdatePhase;
  version: string | null;
  percent: number;
  message: string | null;
}

/** Preload'un renderer'a açtığı köprü. */
export interface UryxBridge {
  settings: {
    get(): Promise<AppSettings>;
    set(patch: Partial<AppSettings>): Promise<AppSettings>;
    reset(): Promise<AppSettings>;
  };
  app: {
    info(): Promise<AppInfo>;
    relaunch(): Promise<void>;
    quit(): Promise<void>;
  };
  updater: {
    getState(): Promise<UpdateState>;
    check(): Promise<UpdateState>;
    respond(action: 'install' | 'later'): Promise<UpdateState>;
  };
  window: {
    minimize(): Promise<void>;
    maximize(): Promise<boolean>;
    show(): Promise<void>;
    hide(): Promise<void>;
    isMaximized(): Promise<boolean>;
  };
  services: {
    status(): Promise<ServicesStatus>;
    start(): Promise<ServicesActionResult>;
    stop(): Promise<ServicesActionResult>;
    restart(service?: string): Promise<ServicesActionResult>;
    logs(service?: string, lines?: number): Promise<string>;
    diagnose(): Promise<ServicesStatus>;
    openDocker(): Promise<ServicesActionResult>;
  };
  host: {
    status(): Promise<HostConnectionState>;
    reconnect(): Promise<HostConnectionState>;
  };
  dialog: {
    openFiles(filters?: { name: string; extensions: string[] }[]): Promise<OpenFilesResult>;
    openFolder(): Promise<OpenFilesResult>;
    saveFile(input?: string | { defaultName?: string; content?: string }): Promise<OpenFilesResult>;
  };
  shell: {
    openPath(path: string): Promise<string>;
    showItemInFolder(path: string): Promise<void>;
  };
  on(channel: IpcEventChannel, listener: (payload: unknown) => void): () => void;
}
