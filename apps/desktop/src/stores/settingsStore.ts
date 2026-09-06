/** Ayar durumu (electron-store ile senkron). */

import { create } from 'zustand';
import { DEFAULT_SETTINGS, type AppSettings } from '@shared/settings';

import { configureApi } from '@/lib/api';
import { applyAccentTheme } from '@/lib/theme';
import { setUiLanguage } from '@/lib/uiLocale';

interface SettingsState {
  settings: AppSettings;
  loaded: boolean;
  saving: boolean;
  error: string | null;
  load: () => Promise<void>;
  update: (patch: Partial<AppSettings>) => Promise<void>;
  reset: () => Promise<void>;
}

/**
 * Ayarlar main process'te saklanır; renderer yalnızca bir yansımasını tutar.
 * Masaüstü köprüsü yoksa (ör. tarayıcıda geliştirme) varsayılanlar kullanılır.
 */
export const useSettingsStore = create<SettingsState>((set, get) => ({
  settings: DEFAULT_SETTINGS,
  loaded: false,
  saving: false,
  error: null,

  load: async () => {
    try {
      const bridge = window.uryx;
      const settings = bridge ? await bridge.settings.get() : DEFAULT_SETTINGS;
      applyAccentTheme(settings.accentTheme);
      configureApi(settings.backendUrl, settings.localToken);
      setUiLanguage(settings.language);
      set({ settings, loaded: true, error: null });
    } catch (error) {
      applyAccentTheme(DEFAULT_SETTINGS.accentTheme);
      configureApi(DEFAULT_SETTINGS.backendUrl, '');
      set({
        settings: DEFAULT_SETTINGS,
        loaded: true,
        error: error instanceof Error ? error.message : String(error),
      });
      setUiLanguage(DEFAULT_SETTINGS.language);
    }
  },

  update: async (patch) => {
    if (patch.accentTheme) applyAccentTheme(patch.accentTheme);
    set({ saving: true, error: null });
    try {
      const bridge = window.uryx;
      const next = bridge
        ? await bridge.settings.set(patch)
        : { ...get().settings, ...patch };
      applyAccentTheme(next.accentTheme);
      configureApi(next.backendUrl, next.localToken);
      setUiLanguage(next.language);
      set({ settings: next, saving: false });
    } catch (error) {
      set({ saving: false, error: error instanceof Error ? error.message : String(error) });
    }
  },

  reset: async () => {
    set({ saving: true });
    try {
      const bridge = window.uryx;
      const next = bridge ? await bridge.settings.reset() : DEFAULT_SETTINGS;
      applyAccentTheme(next.accentTheme);
      configureApi(next.backendUrl, next.localToken);
      setUiLanguage(next.language);
      set({ settings: next, saving: false, error: null });
    } catch (error) {
      set({ saving: false, error: error instanceof Error ? error.message : String(error) });
    }
  },
}));
