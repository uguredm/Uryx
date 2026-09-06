/**
 * Windows masaüstü entegrasyonu.
 *
 * Jump List (görev çubuğu sağ tık), native toast ve ikinci örnek
 * komut satırı bayrakları. AppUserModelId main.ts içinde ayarlanır;
 * toasts'ın görünmesi için bu kimlik şarttır.
 */

import { app, Notification } from 'electron';
import type { UiLanguage } from '@shared/settings';

import { translate } from '../src/lib/messages';
import { getSettings } from './store';
import { sendToRenderer, showMainWindow } from './window';

function isTestProcess(): boolean {
  return Boolean(process.env.VITEST || process.env.URYX_TEST_ROOT);
}

/** Jump List satırları — arayüz dilini izler. */
export function jumpListTasks(language: UiLanguage = 'en'): Array<{
  title: string;
  description: string;
  arguments: string;
}> {
  return [
    {
      arguments: '',
      title: translate(language, 'tray.show'),
      description: translate(language, 'jump.showDesc'),
    },
    {
      arguments: '--new-chat',
      title: translate(language, 'tray.newChat'),
      description: translate(language, 'jump.newChatDesc'),
    },
  ];
}

/** Görev çubuğu Jump List kısayollarını kurar. */
export function installJumpList(): void {
  if (process.platform !== 'win32' || isTestProcess()) return;
  try {
    let language: UiLanguage = 'en';
    try {
      language = getSettings().language;
    } catch {
      language = 'en';
    }
    app.setUserTasks(
      jumpListTasks(language).map((task) => ({
        program: process.execPath,
        arguments: task.arguments,
        iconPath: process.execPath,
        iconIndex: 0,
        title: task.title,
        description: task.description,
      })),
    );
  } catch {
  }
}

/** Komut satırında yeni sohbet istendi mi? */
export function argvRequestsNewChat(argv: string[] = process.argv): boolean {
  return argv.includes('--new-chat');
}

/** İkinci örnek veya Jump List'ten gelen bayrakları uygular. */
export function handleDesktopArgv(argv: string[]): void {
  showMainWindow();
  if (argvRequestsNewChat(argv)) {
    sendToRenderer('tray:newChat');
  }
}

let lastToastAt = 0;
const TOAST_GAP_MS = 20_000;

/** Windows native bildirim (görev çubuğu / Action Center). */
export function notifyDesktop(title: string, body: string): void {
  if (isTestProcess()) return;
  if (!Notification.isSupported()) return;
  const now = Date.now();
  if (now - lastToastAt < TOAST_GAP_MS) return;
  lastToastAt = now;
  try {
    const toast = new Notification({
      title,
      body: body.slice(0, 240),
      silent: true,
    });
    toast.on('click', () => showMainWindow());
    toast.show();
  } catch {
  }
}

const userNotifyTimes: number[] = [];
const USER_NOTIFY_WINDOW_MS = 60_000;
const USER_NOTIFY_MAX = 3;

/**
 * Araç tetikli bildirim (OI ``computer.os.notify``).
 * Sistem tostlarından ayrı; dakikada en fazla 3.
 */
export function notifyDesktopImmediate(title: string, body: string): boolean {
  if (isTestProcess()) return false;
  if (!Notification.isSupported()) return false;
  const now = Date.now();
  while (userNotifyTimes.length > 0 && now - userNotifyTimes[0]! > USER_NOTIFY_WINDOW_MS) {
    userNotifyTimes.shift();
  }
  if (userNotifyTimes.length >= USER_NOTIFY_MAX) return false;
  userNotifyTimes.push(now);
  try {
    const toast = new Notification({
      title: title.slice(0, 80) || 'Uryx',
      body: body.slice(0, 240),
      silent: false,
    });
    toast.on('click', () => showMainWindow());
    toast.show();
    return true;
  } catch {
    return false;
  }
}

/** Testler arasında toast aralığını sıfırlar. */
export function resetDesktopNotifications(): void {
  lastToastAt = 0;
  userNotifyTimes.length = 0;
}
