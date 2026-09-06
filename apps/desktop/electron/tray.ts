/** Sistem tepsisi (tray) menüsü. */

import { app, Menu, nativeImage, Tray, type NativeImage } from 'electron';
import { existsSync } from 'node:fs';
import path from 'node:path';
import type { UiLanguage } from '@shared/settings';

import { translate } from '../src/lib/messages';
import { getSettings } from './store';
import { sendToRenderer, setQuitting, showMainWindow, toggleMainWindow } from './window';

let tray: Tray | null = null;

interface TrayStatus {
  dockerAvailable: boolean;
  apiReachable: boolean;
  hostConnected: boolean;
  engineState?: 'up' | 'starting' | 'down';
}

const trayStatus: TrayStatus = {
  dockerAvailable: true,
  apiReachable: false,
  hostConnected: false,
  engineState: 'down',
};

let trayActions: {
  startServices: () => void;
  openDocker: () => void;
  diagnose: () => void;
} = {
  startServices: () => undefined,
  openDocker: () => undefined,
  diagnose: () => undefined,
};

/** Tepsi menüsünden Docker/servis eylemleri. */
export function setTrayActions(actions: {
  startServices: () => void;
  openDocker: () => void;
  diagnose: () => void;
}): void {
  trayActions = actions;
  rebuildTrayMenu();
}

/** Köprü / Docker durumunu tepsi ipucuna yansıtır. */
export function updateTrayStatus(partial: Partial<TrayStatus>): void {
  Object.assign(trayStatus, partial);
  tray?.setToolTip(trayTooltip());
  rebuildTrayMenu();
}

function uiLanguage(): UiLanguage {
  try {
    return getSettings().language;
  } catch {
    return 'en';
  }
}

/** Docker Desktop / Discord tepsi ipucu — motor starting ≠ kapalı. */
export function formatTrayTooltip(status: TrayStatus, language: UiLanguage = 'en'): string {
  const parts = ['Uryx'];
  parts.push(status.hostConnected ? translate(language, 'tray.bridgeUp') : translate(language, 'tray.bridgeDown'));
  if (status.engineState === 'starting') parts.push(translate(language, 'tray.dockerStarting'));
  else if (!status.dockerAvailable) parts.push(translate(language, 'tray.dockerDown'));
  else if (status.apiReachable) parts.push(translate(language, 'tray.apiReady'));
  else parts.push(translate(language, 'tray.apiWait'));
  return parts.join(' · ');
}

function trayTooltip(): string {
  return formatTrayTooltip(trayStatus, uiLanguage());
}

/**
 * Tepsi simgesini üretir.
 * Paket içindeki ikon bulunamazsa gömülü bir PNG'ye düşer (uygulama açılmalı).
 */
function trayIcon(): NativeImage {
  const candidates = [
    path.join(__dirname, '../../build/tray.png'),
    path.join(__dirname, '../../build/icon.ico'),
    path.join(__dirname, '../../build/icon.png'),
    path.join(process.resourcesPath ?? '', 'tray.png'),
    path.join(process.resourcesPath ?? '', 'icon.ico'),
    path.join(process.resourcesPath ?? '', 'icon.png'),
    path.join(app.getAppPath(), 'build', 'tray.png'),
  ];
  for (const candidate of candidates) {
    if (candidate && existsSync(candidate)) {
      const image = nativeImage.createFromPath(candidate);
      if (!image.isEmpty()) {
        return image.resize({ width: 32, height: 32, quality: 'best' });
      }
    }
  }
  return nativeImage.createFromDataURL(
    'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAAsklEQVRYR+2WMQ6AIAxF6cT/H42TgxNxc3R0cXBwcHBwcHBwcHBwcHBwcHBwcAAnN2jS0FJaoP+SNn3fS1sIgZmdc84555x3zqlUCsA5p1prWWstM8aIUoq1lhH5QQjhnHPgnFPnnFtrBSEEZ+aPUoq11qK1FudcRClFWkvvva+1xowx4pxT7/2/U4QxRpxz4b1X7/2vU4QQcs5Fay3vvf8nQqQUcs6F915K+Z8IERGllFprKaX8T4SIiFprzjl/EyEiQmuNme8iRER47/8S+QBe0zJq6n0nVwAAAABJRU5ErkJggg==',
  );
}

function rebuildTrayMenu(): void {
  if (!tray) return;
  const language = uiLanguage();
  const menu = Menu.buildFromTemplate([
    {
      label: translate(language, 'tray.show'),
      click: () => showMainWindow(),
    },
    {
      label: translate(language, 'tray.newChat'),
      click: () => {
        showMainWindow();
        sendToRenderer('tray:newChat');
      },
    },
    { type: 'separator' },
    {
      label:
        trayStatus.engineState === 'starting'
          ? translate(language, 'tray.dockerWait')
          : trayStatus.dockerAvailable
            ? translate(language, 'tray.startServices')
            : translate(language, 'tray.openDocker'),
      click: () => {
        if (trayStatus.dockerAvailable) trayActions.startServices();
        else trayActions.openDocker();
      },
    },
    {
      label: translate(language, 'tray.diagnose'),
      click: () => trayActions.diagnose(),
    },
    {
      label: translate(language, 'tray.settings'),
      click: () => {
        showMainWindow();
        sendToRenderer('tray:openSettings');
      },
    },
    { type: 'separator' },
    {
      label: translate(language, 'tray.quit'),
      click: () => {
        setQuitting(true);
        app.quit();
      },
    },
  ]);
  tray.setContextMenu(menu);
}

/** Dil değişince tepsi ipucu ve menüyü yeniler. */
export function refreshTrayChrome(): void {
  tray?.setToolTip(trayTooltip());
  rebuildTrayMenu();
}

/** Tepsi menüsünü kurar. */
export function createTray(): Tray {
  if (tray) return tray;

  tray = new Tray(trayIcon());
  tray.setToolTip(trayTooltip());
  rebuildTrayMenu();
  tray.on('click', () => toggleMainWindow());
  tray.on('double-click', () => showMainWindow());

  return tray;
}

/** Tepsi simgesini kaldırır. */
export function destroyTray(): void {
  tray?.destroy();
  tray = null;
}
