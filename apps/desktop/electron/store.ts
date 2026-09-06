/**
 * Yerel ayar deposu (electron-store).
 *
 * Ayarlar kullanıcının `%APPDATA%/Uryx/uryx-settings.json` dosyasında
 * saklanır. Eski `%APPDATA%/Uryx/jarvis-settings.json` ve
 * `%APPDATA%/Jarvis/jarvis-settings.json` bir kez kopyalanır.
 */

import { app } from 'electron';
import { copyFileSync, existsSync, mkdirSync } from 'node:fs';
import path from 'node:path';
import Store from 'electron-store';
import {
  DEFAULT_SETTINGS,
  LLM_PRESET_IDS,
  MCP_SERVERS_STORE_CAP,
  UI_LANGUAGES,
  resolveLlmPreset,
  ttsVoiceForLanguage,
  type AppSettings,
  type McpServerConfig,
  type UiLanguage,
} from '@shared/settings';

import { MCP_TOOL_PATTERN, filterSafeMcpArgs, mcpCommandAllowed } from './host-tools/mcp-guard';
import { sanitizeMcpServerEnv } from './host-tools/mcp-env';
import { setHostLanguage } from './host-i18n';
import { sanitizeAccelerator, sanitizePushToTalkKey } from './hotkeys';

function migrateLegacySettingsFile(): void {
  try {
    const destDir = app.getPath('userData');
    const dest = path.join(destDir, 'uryx-settings.json');
    if (existsSync(dest)) return;
    const candidates = [
      path.join(destDir, 'jarvis-settings.json'),
      path.join(app.getPath('appData'), 'Jarvis', 'jarvis-settings.json'),
    ];
    const legacy = candidates.find((item) => existsSync(item));
    if (!legacy) return;
    mkdirSync(destDir, { recursive: true });
    copyFileSync(legacy, dest);
  } catch {
  }
}

migrateLegacySettingsFile();

type SettingsShape = { settings: AppSettings };
const LEGACY_MODELS = new Set([
  'Qwen/Qwen3-8B-AWQ',
  'Qwen/Qwen3-4B-AWQ',
  'qwen3.8-27b-iq1',
]);
const LEGACY_TOLGA_VOICE = 'windows:Microsoft Tolga - Turkish (Turkey)';

const store = new Store<SettingsShape>({
  name: 'uryx-settings',
  defaults: { settings: DEFAULT_SETTINGS },
  clearInvalidConfig: true,
});

/** Sayısal alanları güvenli aralığa sıkıştırır. */
function clamp(value: unknown, min: number, max: number, fallback: number): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(Math.max(parsed, min), max);
}

/** URL'i doğrular; geçersizse varsayılana döner. */
function safeUrl(value: unknown, fallback: string): string {
  const raw = String(value ?? '').trim();
  if (!raw) return fallback;
  try {
    const url = new URL(raw);
    if (!['http:', 'https:'].includes(url.protocol)) return fallback;
    return raw.replace(/\/+$/, '');
  } catch {
    return fallback;
  }
}

function sanitizeMcpServers(value: unknown): McpServerConfig[] {
  if (!Array.isArray(value)) return [];
  const servers: McpServerConfig[] = [];
  for (const item of value.slice(0, MCP_SERVERS_STORE_CAP)) {
    if (!item || typeof item !== 'object') continue;
    const raw = item as Partial<McpServerConfig>;
    const id = String(raw.id ?? '')
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9_-]/g, '')
      .slice(0, 40);
    const command = String(raw.command ?? '').trim().slice(0, 260);
    if (!id || !mcpCommandAllowed(command)) continue;
    const args = filterSafeMcpArgs(
      (Array.isArray(raw.args) ? raw.args : [])
        .map((arg) => String(arg).slice(0, 200))
        .filter((arg) => arg.length > 0),
      command,
    ).slice(0, 20);
    const allowedTools = (Array.isArray(raw.allowedTools) ? raw.allowedTools : [])
      .map((tool) => String(tool).trim())
      .filter((tool) => MCP_TOOL_PATTERN.test(tool))
      .slice(0, 32);
    const env = sanitizeMcpServerEnv(raw.env);
    servers.push({
      id,
      command,
      args,
      allowedTools,
      ...(Object.keys(env).length > 0 ? { env } : {}),
    });
  }
  return servers;
}

/**
 * Gelen kısmi ayarları doğrular ve normalize eder.
 * Renderer'dan gelen veriye asla doğrudan güvenilmez.
 */
export function sanitizeSettings(patch: Partial<AppSettings>, base: AppSettings): AppSettings {
  const merged = { ...base, ...patch };

  return {
    backendUrl: safeUrl(merged.backendUrl, DEFAULT_SETTINGS.backendUrl),
    vllmUrl: safeUrl(merged.vllmUrl, DEFAULT_SETTINGS.vllmUrl),
    localToken: String(merged.localToken ?? '')
      .trim()
      .slice(0, 256),

    modelName: String(merged.modelName ?? DEFAULT_SETTINGS.modelName).slice(0, 200),
    llmPreset: resolveLlmPreset(
      String(merged.modelName ?? DEFAULT_SETTINGS.modelName),
      (LLM_PRESET_IDS as readonly string[]).includes(String(merged.llmPreset ?? ''))
        ? String(merged.llmPreset)
        : null,
    ),
    contextLength: Math.round(clamp(merged.contextLength, 512, 131_072, 8192)),
    gpuMemoryUtilization: clamp(merged.gpuMemoryUtilization, 0.1, 0.98, 0.7),
    temperature: clamp(merged.temperature, 0, 2, 0.7),
    maxTokens: Math.round(clamp(merged.maxTokens, 64, 32_768, DEFAULT_SETTINGS.maxTokens)),

    whisperModel: String(merged.whisperModel ?? DEFAULT_SETTINGS.whisperModel).slice(0, 60),
    microphoneDeviceId: String(merged.microphoneDeviceId ?? 'default').slice(0, 200),
    micNoiseThreshold: clamp(merged.micNoiseThreshold, 0, 0.5, 0.012),
    adaptiveVadEnabled: Boolean(merged.adaptiveVadEnabled ?? DEFAULT_SETTINGS.adaptiveVadEnabled),
    vadEnabled: Boolean(merged.vadEnabled),
    voiceAutoSend: Boolean(merged.voiceAutoSend),
    vadSilenceTimeoutMs: Math.round(clamp(merged.vadSilenceTimeoutMs, 500, 5000, 1400)),
    followUpListenMs: Math.round(clamp(merged.followUpListenMs, 5000, 120_000, 30_000)),

    ttsEnabled: Boolean(merged.ttsEnabled),
    ttsVoice: ttsVoiceForLanguage(
      (UI_LANGUAGES as readonly string[]).includes(String(merged.language))
        ? (merged.language as UiLanguage)
        : DEFAULT_SETTINGS.language,
      String(merged.ttsVoice ?? DEFAULT_SETTINGS.ttsVoice),
    ),
    ttsSpeed: clamp(merged.ttsSpeed, 0.5, 2, 1),
    ttsVolume: clamp(merged.ttsVolume, 0, 2, 1),

    mcpEnabled: Boolean(merged.mcpEnabled),
    mcpServers: sanitizeMcpServers(merged.mcpServers),

    wakeWordEnabled: Boolean(merged.wakeWordEnabled),
    wakeWord: String(merged.wakeWord ?? DEFAULT_SETTINGS.wakeWord)
      .toLowerCase()
      .slice(0, 40),
    bargeInEnabled: Boolean(merged.bargeInEnabled ?? DEFAULT_SETTINGS.bargeInEnabled),

    autoMemoryEnabled: Boolean(merged.autoMemoryEnabled),
    ragEnabled: Boolean(merged.ragEnabled),
    ragTopK: Math.round(clamp(merged.ragTopK, 1, 20, 5)),

    thinkingMode: Boolean(merged.thinkingMode),
    conciseMode: Boolean(merged.conciseMode),
    toolsEnabled: Boolean(merged.toolsEnabled),

    theme: 'dark', // D23: açık/sistem yok; eski JSON koyuya kilitlenir
    accentTheme: ['green', 'blue'].includes(String(merged.accentTheme))
      ? (merged.accentTheme as AppSettings['accentTheme'])
      : 'green',
    launchOnStartup: Boolean(merged.launchOnStartup),
    minimizeToTray: Boolean(merged.minimizeToTray),
    closeToTray: Boolean(merged.closeToTray),
    globalShortcut: sanitizeAccelerator(
      merged.globalShortcut,
      DEFAULT_SETTINGS.globalShortcut,
    ),
    pushToTalkKey: sanitizePushToTalkKey(merged.pushToTalkKey, DEFAULT_SETTINGS.pushToTalkKey),
    requireRiskConfirmation: Boolean(merged.requireRiskConfirmation),
    language: (UI_LANGUAGES as readonly string[]).includes(String(merged.language))
      ? (merged.language as UiLanguage)
      : DEFAULT_SETTINGS.language,
  };
}

/** Kaydedilmiş ayarları döndürür. */
export function getSettings(): AppSettings {
  const stored = store.get('settings');
  const legacyModel = LEGACY_MODELS.has(String(stored?.modelName ?? ''));
  const legacyVoice = stored?.ttsVoice === LEGACY_TOLGA_VOICE;
  const storedPresetMissing = stored != null && !('llmPreset' in stored);
  const migrated =
    legacyModel || legacyVoice
      ? {
          ...stored,
          modelName: legacyModel ? DEFAULT_SETTINGS.modelName : stored.modelName,
          maxTokens:
            legacyModel && stored.maxTokens === 2048
              ? DEFAULT_SETTINGS.maxTokens
              : stored.maxTokens,
          ttsVoice: legacyVoice ? DEFAULT_SETTINGS.ttsVoice : stored.ttsVoice,
        }
      : stored;
  const withPreset = storedPresetMissing
    ? {
        ...migrated,
        llmPreset: resolveLlmPreset(String(migrated?.modelName ?? DEFAULT_SETTINGS.modelName)),
      }
    : migrated;
  const settings = sanitizeSettings(withPreset ?? {}, DEFAULT_SETTINGS);
  if (legacyModel || legacyVoice || storedPresetMissing) store.set('settings', settings);
  setHostLanguage(settings.language);
  return settings;
}

/** Ayarları kısmi olarak günceller ve normalize edilmiş sonucu döndürür. */
export function updateSettings(patch: Partial<AppSettings>): AppSettings {
  const next = sanitizeSettings(patch ?? {}, getSettings());
  store.set('settings', next);
  setHostLanguage(next.language);
  return next;
}

/** Ayarları varsayılana döndürür. */
export function resetSettings(): AppSettings {
  store.set('settings', DEFAULT_SETTINGS);
  setHostLanguage(DEFAULT_SETTINGS.language);
  return DEFAULT_SETTINGS;
}

/** Ayar dosyasının tam yolu (arayüzde gösterilir). */
export function settingsPath(): string {
  return store.path;
}
