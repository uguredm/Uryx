import type {
  AppInfo,
  HostConnectionState,
  IpcEventChannel,
  OpenFilesResult,
  ServicesActionResult,
  ServicesStatus,
  UpdateState,
} from '@shared/ipc';
import type { AppSettings } from '@shared/settings';

/** Preload'un `window.uryx` üzerinden açtığı köprü. */
export interface UryxWindowBridge {
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
    status(): Promise<ServicesStatus & { repoRoot: string | null }>;
    start(): Promise<ServicesActionResult>;
    stop(): Promise<ServicesActionResult>;
    restart(service?: string): Promise<ServicesActionResult>;
    logs(service?: string, lines?: number): Promise<string>;
    diagnose(): Promise<ServicesStatus & { repoRoot: string | null }>;
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
  wake: {
    status(): Promise<{
      engine: 'onnx' | 'whisper_fallback';
      modelPresent: boolean;
      modelsHint: string;
      usingFallback: boolean;
    }>;
    pushPcm(
      samples: number[],
      sampleRate: number,
    ): Promise<{ hit: boolean; score: number; reason: string }>;
  };
  on(channel: IpcEventChannel, listener: (payload: unknown) => void): () => void;
}

declare global {
  interface Window {
    uryx?: UryxWindowBridge;
    isUryxDesktop?: boolean;
  }
}

export {};
