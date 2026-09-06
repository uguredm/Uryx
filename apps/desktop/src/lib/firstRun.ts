/**
 * İlk çalıştırma hazırlık listesi — AnythingLLM `onboarding_complete`
 * ve Jan `setupCompleted` deseni. Sihirbaz değil; HUD'u kilitlemez.
 */

import type { UiLanguage } from '@shared/settings';

import { translate } from '@/lib/i18n';

export const FIRST_RUN_DISMISS_KEY = 'uryx.firstRun.dismissed';

export interface ReadinessItem {
  id: string;
  label: string;
  ready: boolean;
  hint: string;
  action: 'system' | 'settings' | null;
}

export interface ReadinessInput {
  chatOpen: boolean;
  modelLoaded: boolean | null;
  downServices: string[];
  mcpEnabled?: boolean;
  mcpServerCount?: number;
  language?: UiLanguage;
}

export function buildReadiness(input: ReadinessInput): ReadinessItem[] {
  const lang = input.language ?? 'en';
  const serviceReady = input.downServices.length === 0 && input.modelLoaded !== null;
  const items: ReadinessItem[] = [
    {
      id: 'api',
      label: translate(lang, 'firstRun.api'),
      ready: input.chatOpen,
      hint: input.chatOpen
        ? translate(lang, 'firstRun.apiOk')
        : translate(lang, 'firstRun.apiWait'),
      action: 'system',
    },
    {
      id: 'model',
      label: translate(lang, 'firstRun.model'),
      ready: input.modelLoaded === true,
      hint:
        input.modelLoaded === true
          ? translate(lang, 'firstRun.modelOk')
          : input.modelLoaded === false
            ? translate(lang, 'firstRun.modelDown')
            : translate(lang, 'firstRun.modelWait'),
      action: 'system',
    },
    {
      id: 'services',
      label: translate(lang, 'firstRun.services'),
      ready: serviceReady && input.downServices.length === 0 && input.chatOpen,
      hint:
        input.downServices.length > 0
          ? translate(lang, 'firstRun.servicesDown', {
              names: input.downServices.slice(0, 3).join(', '),
            })
          : input.chatOpen
            ? translate(lang, 'firstRun.servicesOk')
            : translate(lang, 'firstRun.servicesWait'),
      action: 'system',
    },
  ];
  if (input.mcpEnabled) {
    const count = input.mcpServerCount ?? 0;
    items.push({
      id: 'mcp',
      label: translate(lang, 'firstRun.mcp'),
      ready: count > 0,
      hint: count > 0 ? translate(lang, 'firstRun.mcpOk') : translate(lang, 'firstRun.mcpWait'),
      action: 'settings',
    });
  }
  return items;
}

export function isFirstRunDismissed(): boolean {
  if (typeof localStorage === 'undefined') return false;
  try {
    return localStorage.getItem(FIRST_RUN_DISMISS_KEY) === '1';
  } catch {
    return false;
  }
}

export function dismissFirstRun(): void {
  try {
    localStorage.setItem(FIRST_RUN_DISMISS_KEY, '1');
  } catch {
  }
}

export function shouldShowFirstRun(items: ReadinessItem[], dismissed: boolean): boolean {
  if (dismissed) return false;
  return items.some((item) => !item.ready);
}
