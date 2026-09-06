/**
 * Ana pencere yönetimi.
 *
 * Güvenlik: `nodeIntegration` kapalı, `contextIsolation` ve `sandbox` açık,
 * `webSecurity` etkin. Renderer Node API'lerine erişemez; tüm ayrıcalıklı
 * işlemler preload üzerinden whitelist'li IPC ile main process'e gider.
 */

import { BrowserWindow, shell } from 'electron';
import path from 'node:path';

import { resolveAppIconPath } from './app-icon';
import { getSettings } from './store';

let mainWindow: BrowserWindow | null = null;
/** Uygulama gerçekten kapanıyor mu (tray'e küçültme değil)? */
let quitting = false;

/** Uygulamanın kapanış aşamasında olduğunu işaretler. */
export function setQuitting(value: boolean): void {
  quitting = value;
}

export function isQuitting(): boolean {
  return quitting;
}

/** Ana pencereyi döndürür. */
export function getMainWindow(): BrowserWindow | null {
  return mainWindow;
}

/** Ana pencereyi oluşturur. */
export function createMainWindow(): BrowserWindow {
  if (mainWindow && !mainWindow.isDestroyed()) return mainWindow;

  const window = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 680,
    show: false,
    title: 'Uryx',
    backgroundColor: '#070b14',
    autoHideMenuBar: true,
    icon: resolveAppIconPath(),
    webPreferences: {
      preload: path.join(__dirname, '../preload/index.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      webSecurity: true,
      allowRunningInsecureContent: false,
      experimentalFeatures: false,
      spellcheck: false,
    },
  });

  window.once('ready-to-show', () => window.show());

  window.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//i.test(url)) void shell.openExternal(url);
    return { action: 'deny' };
  });

  window.webContents.on('will-navigate', (event, url) => {
    const devServer = process.env.ELECTRON_RENDERER_URL;
    const allowed = devServer ? url.startsWith(devServer) : url.startsWith('file://');
    if (!allowed) {
      event.preventDefault();
      if (/^https?:\/\//i.test(url)) void shell.openExternal(url);
    }
  });

  window.webContents.session.setPermissionRequestHandler((_wc, permission, callback) => {
    callback(permission === 'media');
  });

  window.on('close', (event) => {
    const settings = getSettings();
    if (!quitting && settings.closeToTray) {
      event.preventDefault();
      window.hide();
    }
  });

  window.on('minimize', () => {
    if (getSettings().minimizeToTray) {
      window.hide();
    }
  });

  window.on('closed', () => {
    mainWindow = null;
  });

  loadRenderer(window);
  mainWindow = window;
  return window;
}

/** Renderer içeriğini yükler (dev sunucu veya derlenmiş dosya). */
function loadRenderer(window: BrowserWindow): void {
  const devServerUrl = process.env.ELECTRON_RENDERER_URL;
  if (devServerUrl) {
    void window.loadURL(devServerUrl);
    window.webContents.openDevTools({ mode: 'detach' });
  } else {
    void window.loadFile(path.join(__dirname, '../renderer/index.html'));
  }
}

/** Pencereyi gösterir ve öne getirir. */
export function showMainWindow(): void {
  const window = mainWindow ?? createMainWindow();
  if (window.isMinimized()) window.restore();
  window.show();
  window.focus();
}

/** Pencereyi gösterir/gizler (global kısayol). */
export function toggleMainWindow(): void {
  const window = mainWindow ?? createMainWindow();
  if (window.isVisible() && window.isFocused()) {
    window.hide();
  } else {
    showMainWindow();
  }
}

/** Renderer'a olay gönderir. */
export function sendToRenderer(channel: string, payload?: unknown): void {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send(channel, payload);
  }
}
