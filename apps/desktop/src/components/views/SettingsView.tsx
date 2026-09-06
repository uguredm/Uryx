/** Ayarlar ekranı. */

import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { RotateCcw, Save, RefreshCw } from 'lucide-react';
import {
  LLM_PRESETS,
  MCP_RECIPE_CATALOG,
  MCP_SERVERS_STORE_CAP,
  applyRecommendedMcpServers,
  clearAllMcpServers,
  describeMcpServersJson,
  filterMcpRecipeCatalog,
  mcpSettingsFormDirty,
  parseMcpServersJson,
  keepRecommendedMcpServers,
  cloneMcpRecipeById,
  cloneRecommendedMcpServers,
  hasMcpServer,
  mcpNativeOverlapNote,
  mcpRecipeGroupActive,
  setMcpRecipeEnabled,
  setMcpRecipeGroupEnabled,
  setMcpServerEnvValue,
  defaultTtsVoiceForLanguage,
  WINDOWS_TURKISH_VOICE,
  type AppSettings,
  type LlmPreset,
  type McpRecipeMeta,
  type McpServerConfig,
} from '@shared/settings';

import { AccentThemePicker } from '@/components/common/AccentThemePicker';
import { detectCloudProvider } from '@/lib/cloudProvider';
import { useI18n, type MessageKey, MESSAGE_TABLES } from '@/lib/i18n';
import { displaySafePath } from '@/lib/displaySafePath';
import { InfoRow, Toggle, ViewHeader } from '@/components/common/Primitives';
import { SecretInput } from '@/components/common/SecretInput';
import { api } from '@/lib/api';
import { listMicrophones } from '@/lib/audio';
import { cn } from '@/lib/cn';
import { formatDecimal } from '@/lib/format';
import { whisperGpuContentionHint } from '@/lib/whisperReload';
import { useSettingsStore } from '@/stores/settingsStore';
import { useUIStore } from '@/stores/uiStore';

const WHISPER_MODELS = ['tiny', 'base', 'small', 'medium', 'large-v3', 'distil-large-v3'];

export function SettingsView(): JSX.Element {
  const { settings, update, reset, saving } = useSettingsStore();
  const { t, language } = useI18n();
  const pushToast = useUIStore((state) => state.pushToast);

  const [draft, setDraft] = useState<AppSettings>(settings);
  const [settingsQuery, setSettingsQuery] = useState('');
  const [microphones, setMicrophones] = useState<{ deviceId: string; label: string }[]>([]);
  const [checkingUpdate, setCheckingUpdate] = useState(false);
  const [mcpJson, setMcpJson] = useState(() => JSON.stringify(settings.mcpServers, null, 2));
  const [mcpCatalogQuery, setMcpCatalogQuery] = useState('');
  const [geminiKey, setGeminiKey] = useState('');
  const [geminiKeyTouched, setGeminiKeyTouched] = useState(false);
  const [geminiModel, setGeminiModel] = useState<string | null>(null);
  const skipGeminiTouch = useRef(false);

  useEffect(() => {
    setDraft(settings);
    setMcpJson(JSON.stringify(settings.mcpServers, null, 2));
  }, [settings]);

  useEffect(() => {
    void listMicrophones()
      .then(setMicrophones)
      .catch(() => setMicrophones([]));
  }, []);

  const voices = useQuery({
    queryKey: ['tts-voices'],
    queryFn: () => api.speech.voices(),
    retry: 0,
  });
  const sttStatus = useQuery({
    queryKey: ['stt-status'],
    queryFn: () => api.speech.sttStatus(),
    retry: 0,
  });
  const appInfo = useQuery({
    queryKey: ['app-info'],
    queryFn: async () => window.uryx?.app.info() ?? null,
    enabled: Boolean(window.uryx),
    staleTime: Infinity,
  });
  const effectiveConfig = useQuery({
    queryKey: ['system-config'],
    queryFn: () => api.system.config(),
    retry: 0,
  });
  const llmCredentials = useQuery({
    queryKey: ['llm-credentials'],
    queryFn: () => api.system.llmCredentials(),
    retry: 0,
  });
  const rawLlmConfig = effectiveConfig.data?.llm;
  const llmConfig =
    rawLlmConfig && typeof rawLlmConfig === 'object'
      ? (rawLlmConfig as Record<string, unknown>)
      : {};
  const geminiStatus = llmCredentials.data;
  const geminiModelDraft = geminiModel ?? geminiStatus?.model ?? '';
  const geminiDirty =
    geminiKeyTouched || (geminiStatus != null && geminiModelDraft !== geminiStatus.model);
  const liveProvider = detectCloudProvider(geminiKeyTouched ? geminiKey : '', geminiModelDraft);
  const providerLabel = liveProvider?.label ?? geminiStatus?.provider_label;

  const dirty =
    JSON.stringify(draft) !== JSON.stringify(settings) ||
    geminiDirty ||
    mcpSettingsFormDirty(settings.mcpServers, mcpJson);
  const set = <K extends keyof AppSettings>(key: K, value: AppSettings[K]): void =>
    setDraft((current) => ({ ...current, [key]: value }));

  const applyLanguage = (next: AppSettings['language']): void => {
    const ttsVoice = defaultTtsVoiceForLanguage(next);
    setDraft((current) => ({ ...current, language: next, ttsVoice }));
    void update({ language: next, ttsVoice });
  };

  const applyLlmPreset = (id: LlmPreset): void => {
    const spec = LLM_PRESETS[id];
    setDraft((current) => ({
      ...current,
      llmPreset: id,
      modelName: spec.modelName,
      contextLength: spec.contextLength,
    }));
  };

  const save = async (): Promise<void> => {
    const mcpState = describeMcpServersJson(mcpJson, language);
    if (!mcpState.ok) {
      pushToast('error', mcpState.error);
      return;
    }
    const parsed = parseMcpServersJson(mcpJson);
    const servers = parsed ?? draft.mcpServers;
    const previousWhisper = settings.whisperModel;
    await update({ ...draft, mcpServers: servers });
    if (draft.whisperModel !== previousWhisper) {
      try {
        await api.speech.reloadStt(draft.whisperModel);
        await sttStatus.refetch();
      } catch (error) {
        pushToast(
          'error',
          error instanceof Error ? error.message : t('settings.whisperReloadFail'),
        );
        return;
      }
    }
    if (geminiDirty) {
      try {
        await api.system.putLlmCredentials({
          api_key: geminiKeyTouched ? geminiKey : undefined,
          model: geminiModelDraft.trim() || undefined,
        });
        setGeminiKey('');
        setGeminiKeyTouched(false);
        setGeminiModel(null);
        await Promise.all([effectiveConfig.refetch(), llmCredentials.refetch()]);
      } catch (error) {
        pushToast(
          'error',
          error instanceof Error ? error.message : t('settings.cloudSaveFail'),
        );
        return;
      }
    }
    pushToast('success', t('settings.toast.saved'));
  };

  const applyMcpServers = (servers: McpServerConfig[]): void => {
    setMcpJson(JSON.stringify(servers, null, 2));
    set('mcpServers', servers);
  };

  const currentMcpServers = (): McpServerConfig[] =>
    parseMcpServersJson(mcpJson) ?? draft.mcpServers;

  const toggleMcpCard = (id: string, enabled: boolean): void => {
    const recipe = cloneMcpRecipeById(id);
    if (!recipe) return;
    applyMcpServers(setMcpRecipeEnabled(currentMcpServers(), recipe, enabled));
  };

  const setMcpCardEnv = (id: string, key: string, value: string): void => {
    applyMcpServers(setMcpServerEnvValue(currentMcpServers(), id, key, value));
  };

  const visibleMcpCatalog = filterMcpRecipeCatalog(MCP_RECIPE_CATALOG, mcpCatalogQuery);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <ViewHeader
        title={t('view.settings')}
        description={t('view.settings.desc')}
        actions={
          <>
            <button
              type="button"
              className="btn-outline"
              onClick={() => {
                void reset();
                pushToast('info', t('settings.toast.reset'));
              }}
            >
              <RotateCcw size={14} />
              {t('settings.reset')}
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={() => void save()}
              disabled={!dirty || saving}
            >
              <Save size={14} />
              {saving ? t('settings.saving') : t('settings.save')}
            </button>
          </>
        }
      />

      <div className="scroll-area flex-1 p-6">
        <div className="mx-auto max-w-2xl space-y-5">
          <label className="block">
            <span className="sr-only">{t('settings.search')}</span>
            <input
              value={settingsQuery}
              onChange={(event) => setSettingsQuery(event.target.value)}
              placeholder={t('settings.search')}
              className="input"
            />
          </label>
          <Section
            title={t('settings.language')}
            description={t('settings.languageHint')}
            filter={settingsQuery}
            keywords="dil language english türkçe turkish"
          >
            <div className="flex gap-2">
              <button
                type="button"
                className={cn('btn-outline', draft.language === 'tr' && 'ring-1 ring-uryx-accent')}
                onClick={() => applyLanguage('tr')}
              >
                {t('settings.lang.tr')}
              </button>
              <button
                type="button"
                className={cn('btn-outline', draft.language === 'en' && 'ring-1 ring-uryx-accent')}
                onClick={() => applyLanguage('en')}
              >
                {t('settings.lang.en')}
              </button>
            </div>
          </Section>
          {/* Bağlantı */}
          <Section
            title={t('settings.section.connection')}
            description={t('settings.section.connectionDesc')}
            filter={settingsQuery}
          >
            <Field label={t('settings.field.backend')} hint={t('settings.field.backendHint')}>
              <input
                value={draft.backendUrl}
                onChange={(event) => set('backendUrl', event.target.value)}
                className="input"
                placeholder="http://127.0.0.1:8080"
              />
            </Field>
            <Field label={t('settings.field.llm')} hint={t('settings.field.llmHint')}>
              <input
                value={draft.vllmUrl}
                onChange={(event) => set('vllmUrl', event.target.value)}
                className="input"
                placeholder="http://127.0.0.1:8000/v1"
              />
            </Field>
            <Field
              label={t('settings.field.token')}
              hint={t('settings.field.tokenHint')}
            >
              <SecretInput
                value={draft.localToken}
                onChange={(value) => set('localToken', value)}
                className="font-mono"
                placeholder={t('settings.field.tokenEmpty')}
                autoComplete="off"
              />
            </Field>
          </Section>

          {/* Model */}
          <Section
            title={t('settings.section.model')}
            description={t('settings.section.modelDesc')}
            filter={settingsQuery}
          >
            <div className="border-b border-uryx-border pb-3">
              <InfoRow
                label={t('settings.hybrid')}
                value={String(llmConfig.routing_mode ?? 'local')}
              />
              <InfoRow
                label={t('settings.cloudApi')}
                value={
                  geminiStatus?.configured
                    ? geminiStatus.source === 'env'
                      ? t('settings.cloud.connectedEnv')
                      : t('settings.cloud.connected')
                    : llmConfig.cloud_configured === true
                      ? t('settings.cloud.connected')
                      : t('settings.cloud.missing')
                }
              />
              {providerLabel ? (
                <InfoRow label={t('settings.providerDetected')} value={providerLabel} />
              ) : geminiKeyTouched && geminiKey.trim().startsWith('sk-ant-') ? (
                <InfoRow
                  label={t('settings.providerDetected')}
                  value={t('settings.cloud.claudeHint')}
                />
              ) : null}
              {geminiStatus?.configured && geminiStatus.hint ? (
                <InfoRow label={t('settings.keyHintLabel')} value={`···${geminiStatus.hint}`} />
              ) : null}
            </div>
            <Field
              label={t('settings.cloudKey')}
              hint={t('settings.cloudKeyHint')}
            >
              <SecretInput
                value={geminiKey}
                onChange={(value) => {
                  if (skipGeminiTouch.current) {
                    skipGeminiTouch.current = false;
                    setGeminiKey(value);
                    return;
                  }
                  setGeminiKey(value);
                  setGeminiKeyTouched(true);
                }}
                className="font-mono"
                placeholder={
                  geminiStatus?.configured
                    ? t('settings.cloud.savedPh', { hint: geminiStatus.hint })
                    : t('settings.field.tokenEmpty')
                }
                autoComplete="off"
                onReveal={
                  geminiStatus?.configured
                    ? async () => {
                        skipGeminiTouch.current = true;
                        try {
                          const revealed = await api.system.revealLlmCredentials();
                          return revealed.api_key;
                        } catch (error) {
                          skipGeminiTouch.current = false;
                          throw error;
                        }
                      }
                    : undefined
                }
              />
            </Field>
            <Field
              label={t('settings.cloudModel')}
              hint={t('settings.cloudModelHint')}
            >
              <input
                value={geminiModelDraft}
                onChange={(event) => setGeminiModel(event.target.value)}
                className="input font-mono"
                placeholder={
                  liveProvider?.defaultModel ||
                  geminiStatus?.model ||
                  t('settings.cloud.modelPh')
                }
              />
            </Field>
            {geminiStatus?.source === 'ui' && (
              <button
                type="button"
                className="btn-outline"
                onClick={() => {
                  void (async () => {
                    try {
                      await api.system.deleteLlmCredentials();
                      setGeminiKey('');
                      setGeminiKeyTouched(false);
                      setGeminiModel(null);
                      await Promise.all([effectiveConfig.refetch(), llmCredentials.refetch()]);
                      pushToast('success', t('settings.cloud.cleared'));
                    } catch (error) {
                      pushToast(
                        'error',
                        error instanceof Error ? error.message : t('settings.cloud.clearFail'),
                      );
                    }
                  })();
                }}
              >
                {t('settings.cloud.clearBtn')}
              </button>
            )}
            <Field
              label={t('settings.localModel')}
              hint={t('settings.localModelHint')}
            >
              <div className="grid gap-3 sm:grid-cols-2">
                {(Object.values(LLM_PRESETS) as (typeof LLM_PRESETS)[LlmPreset][]).map((spec) => {
                  const selected = draft.llmPreset === spec.id;
                  const hasFile = Boolean(appInfo.data?.ggufFiles.includes(spec.ggufFile));
                  return (
                    <button
                      key={spec.id}
                      type="button"
                      onClick={() => applyLlmPreset(spec.id)}
                      className={cn(
                        'rounded-lg border p-3 text-left transition-colors',
                        selected
                          ? 'border-uryx-accent bg-uryx-accent/10'
                          : 'border-uryx-border hover:border-slate-500',
                      )}
                    >
                      <strong className="block text-sm text-slate-100">
                        {t(`settings.preset.${spec.id}.label` as MessageKey)}
                      </strong>
                      <span className="mt-1 block text-[12px] leading-snug text-slate-400">
                        {t(`settings.preset.${spec.id}.desc` as MessageKey)}
                      </span>
                      <span className="mt-2 block font-mono text-[11px] text-slate-500">
                        {spec.ggufFile}
                      </span>
                      {appInfo.data ? (
                        <span
                          className={cn(
                            'mt-1 block text-[11px]',
                            hasFile ? 'text-emerald-400' : 'text-amber-400',
                          )}
                        >
                          {hasFile ? t('settings.ggufReady') : t('settings.ggufMissing')}
                        </span>
                      ) : null}
                    </button>
                  );
                })}
              </div>
              {appInfo.data?.modelsDir ? (
                <p className="mt-2 font-mono text-[11px] text-slate-500">
                  {t('settings.about.modelsHint')}
                </p>
              ) : null}
            </Field>
            <Field
              label={t('settings.modelName')}
              hint={t('settings.modelNameHint')}
            >
              <input
                value={draft.modelName}
                onChange={(event) => set('modelName', event.target.value)}
                className="input"
                placeholder="qwen3-8b"
              />
            </Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field
                label={t('settings.context')}
                hint={t('settings.contextHint')}
              >
                <input
                  type="number"
                  min={512}
                  max={131072}
                  step={512}
                  value={draft.contextLength}
                  onChange={(event) => set('contextLength', Number(event.target.value))}
                  className="input"
                />
              </Field>
              <Field label={t('settings.temperature')}>
                <input
                  type="number"
                  min={0}
                  max={2}
                  step={0.05}
                  value={draft.temperature}
                  onChange={(event) => set('temperature', Number(event.target.value))}
                  className="input"
                />
              </Field>
              <Field label={t('settings.maxTokens')}>
                <input
                  type="number"
                  min={64}
                  max={32768}
                  step={64}
                  value={draft.maxTokens}
                  onChange={(event) => set('maxTokens', Number(event.target.value))}
                  className="input"
                />
              </Field>
            </div>
            <Toggle
              checked={draft.thinkingMode}
              onChange={(value) => set('thinkingMode', value)}
              label={t('settings.thinking')}
              description={t('settings.thinkingDesc')}
            />
            <Toggle
              checked={draft.conciseMode}
              onChange={(value) => set('conciseMode', value)}
              label={t('settings.concise')}
              description={t('settings.conciseDesc')}
            />
            <Toggle
              checked={draft.toolsEnabled}
              onChange={(value) => set('toolsEnabled', value)}
              label={t('settings.toolsUse')}
              description={t('settings.toolsUseDesc')}
            />
          </Section>

          {/* Konuşma tanıma */}
          <Section
            title={t('settings.section.stt')}
            description={
              sttStatus.data
                ? t('settings.sttActive', {
                    model: sttStatus.data.model || '—',
                    device: sttStatus.data.device || '—',
                  })
                : t('settings.section.sttDesc')
            }
            filter={settingsQuery}
          >
            <Field
              label={t('settings.whisperModel')}
              hint={
                whisperGpuContentionHint(draft.whisperModel, sttStatus.data?.device ?? '') ??
                t('settings.whisperHint')
              }
            >
              <select
                value={draft.whisperModel}
                onChange={(event) => set('whisperModel', event.target.value)}
                className="input"
              >
                {WHISPER_MODELS.map((model) => (
                  <option key={model} value={model}>
                    {model}
                  </option>
                ))}
              </select>
            </Field>
            <Field label={t('settings.mic')}>
              <select
                value={draft.microphoneDeviceId}
                onChange={(event) => set('microphoneDeviceId', event.target.value)}
                className="input"
              >
                <option value="default">{t('settings.micDefault')}</option>
                {microphones.map((device) => (
                  <option key={device.deviceId} value={device.deviceId}>
                    {device.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field
              label={t('settings.noise', {
                n: formatDecimal(draft.micNoiseThreshold.toFixed(3), language),
              })}
              hint={t('settings.noiseHint')}
            >
              <input
                type="range"
                min={0.002}
                max={0.08}
                step={0.002}
                value={draft.micNoiseThreshold}
                onChange={(event) => set('micNoiseThreshold', Number(event.target.value))}
                className="w-full accent-uryx-accent"
              />
            </Field>
            <Toggle
              checked={draft.adaptiveVadEnabled}
              onChange={(value) => set('adaptiveVadEnabled', value)}
              label={t('settings.autoNoise')}
              description={t('settings.autoNoiseDesc')}
            />
            <Toggle
              checked={draft.vadEnabled}
              onChange={(value) => set('vadEnabled', value)}
              label={t('settings.vad')}
              description={t('settings.vadDesc')}
            />
            <Toggle
              checked={draft.voiceAutoSend}
              onChange={(value) => set('voiceAutoSend', value)}
              label={t('settings.autoSend')}
              description={t('settings.autoSendDesc')}
            />
            <Field
              label={t('settings.silence', {
                n: formatDecimal((draft.vadSilenceTimeoutMs / 1000).toFixed(1), language),
              })}
            >
              <input
                type="range"
                min={700}
                max={3000}
                step={100}
                value={draft.vadSilenceTimeoutMs}
                onChange={(event) => set('vadSilenceTimeoutMs', Number(event.target.value))}
                className="w-full accent-uryx-accent"
                disabled={!draft.vadEnabled}
              />
            </Field>
            <Field
              label={t('settings.followUp', { n: Math.round(draft.followUpListenMs / 1000) })}
              hint={t('settings.followUpHint')}
            >
              <input
                type="range"
                min={5000}
                max={60000}
                step={5000}
                value={draft.followUpListenMs}
                onChange={(event) => set('followUpListenMs', Number(event.target.value))}
                className="w-full accent-uryx-accent"
              />
            </Field>
          </Section>

          {/* Seslendirme */}
          <Section
            title={t('settings.section.tts')}
            description={t('settings.section.ttsDesc')}
            filter={settingsQuery}
          >
            <Toggle
              checked={draft.ttsEnabled}
              onChange={(value) => set('ttsEnabled', value)}
              label={t('settings.ttsEnable')}
              description={t('settings.ttsEnableDesc')}
            />
            <Field label={t('settings.voice')}>
              <select
                value={draft.ttsVoice}
                onChange={(event) => set('ttsVoice', event.target.value)}
                className="input"
              >
                <option value="en-US-GuyNeural">{t('settings.voice.guy')}</option>
                <option value="en-US-JennyNeural">{t('settings.voice.jenny')}</option>
                <option value="tr-TR-AhmetNeural">{t('settings.voice.ahmet')}</option>
                <option value="tr-TR-EmelNeural">{t('settings.voice.emel')}</option>
                <option value="tr_TR-dfki-medium">{t('settings.voice.piper')}</option>
                <option value="en_US-lessac-medium">{t('settings.voice.lessac')}</option>
                <option value={WINDOWS_TURKISH_VOICE}>{t('settings.voice.tolga')}</option>
                {(voices.data?.voices ?? [])
                  .filter(
                    (voice) =>
                      ![
                        'en-US-GuyNeural',
                        'en-US-JennyNeural',
                        'tr-TR-AhmetNeural',
                        'tr-TR-EmelNeural',
                        'tr_TR-dfki-medium',
                        'en_US-lessac-medium',
                      ].includes(voice.id),
                  )
                  .map((voice) => (
                    <option key={voice.id} value={voice.id}>
                      {voice.name}
                      {voice.installed ? '' : t('settings.voicePending')}
                    </option>
                  ))}
              </select>
            </Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label={t('settings.ttsSpeed', { n: formatDecimal(draft.ttsSpeed.toFixed(2), language) })}>
                <input
                  type="range"
                  min={0.5}
                  max={2}
                  step={0.05}
                  value={draft.ttsSpeed}
                  onChange={(event) => set('ttsSpeed', Number(event.target.value))}
                  className="w-full accent-uryx-accent"
                />
              </Field>
              <Field label={t('settings.ttsVolume', { n: Math.round(draft.ttsVolume * 100) })}>
                <input
                  type="range"
                  min={0}
                  max={1.5}
                  step={0.05}
                  value={draft.ttsVolume}
                  onChange={(event) => set('ttsVolume', Number(event.target.value))}
                  className="w-full accent-uryx-accent"
                />
              </Field>
            </div>
          </Section>

          {/* Wake word */}
          <Section
            title={t('settings.section.wake')}
            description={t('settings.section.wakeDesc')}
            filter={settingsQuery}
          >
            <Toggle
              checked={draft.wakeWordEnabled}
              onChange={(value) => set('wakeWordEnabled', value)}
              label={t('settings.wakeEnable')}
              description={t('settings.wakeEnableDesc')}
            />
            <Field label={t('settings.wakePhrase')}>
              <input
                value={draft.wakeWord}
                onChange={(event) => set('wakeWord', event.target.value)}
                className="input"
                disabled={!draft.wakeWordEnabled}
              />
            </Field>
            <Toggle
              checked={draft.bargeInEnabled}
              onChange={(value) => set('bargeInEnabled', value)}
              label={t('settings.barge')}
              description={t('settings.bargeDesc')}
              disabled={!draft.wakeWordEnabled}
            />
          </Section>

          {/* MCP */}
          <Section
            title={t('settings.section.mcp')}
            description={t('settings.mcpSectionDesc')}
            filter={settingsQuery}
            keywords="playwright github brave huggingface weather wikipedia arxiv wikidata youtube hn ddg duckduckgo openlibrary translate libretranslate rss geocode nominatim osm tarif mcp_call fetch time docs think web_search wiki_lookup fx_rate frankfurter overlap"
          >
            <Toggle
              checked={draft.mcpEnabled}
              onChange={(value) => {
                set('mcpEnabled', value);
                if (value) {
                  const parsed = parseMcpServersJson(mcpJson);
                  if (parsed && parsed.length === 0) {
                    applyMcpServers(cloneRecommendedMcpServers());
                  }
                }
              }}
              label={t('settings.mcpEnable')}
              description={t('settings.mcpEnableDesc')}
            />
            <p className="text-[11.5px] leading-relaxed text-slate-600">{t('settings.mcpOverlap')}</p>
            <p className="text-[11.5px] leading-relaxed text-slate-600">{t('settings.mcpFirstRun')}</p>
            <Field label={t('settings.mcpSearch')} hint={t('settings.mcpSearchHint')}>
              <input
                value={mcpCatalogQuery}
                onChange={(event) => setMcpCatalogQuery(event.target.value)}
                className="input"
                placeholder={t('settings.mcpSearchPh')}
                disabled={!draft.mcpEnabled}
              />
            </Field>
            {(['recommended', 'code', 'search', 'knowledge'] as const).map((group) => {
              const cards = visibleMcpCatalog.filter((card) => card.group === group);
              if (cards.length === 0) return null;
              const servers = parseMcpServersJson(mcpJson) ?? draft.mcpServers;
              return (
                <McpRecipeGroup
                  key={group}
                  t={t}
                  title={t(
                    group === 'code'
                      ? 'settings.mcp.group.code'
                      : group === 'search'
                        ? 'settings.mcp.group.search'
                        : group === 'knowledge'
                          ? 'settings.mcp.group.knowledge'
                          : 'settings.mcp.group.recommended',
                  )}
                  cards={cards}
                  servers={servers}
                  disabled={!draft.mcpEnabled}
                  groupActive={mcpRecipeGroupActive(servers, group)}
                  onGroupToggle={(enabled) =>
                    applyMcpServers(setMcpRecipeGroupEnabled(currentMcpServers(), group, enabled))
                  }
                  onToggle={toggleMcpCard}
                  onEnv={setMcpCardEnv}
                />
              );
            })}
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                className="btn-outline h-8 py-1 text-xs"
                disabled={!draft.mcpEnabled}
                onClick={() => {
                  applyMcpServers(
                    applyRecommendedMcpServers(parseMcpServersJson(mcpJson) ?? draft.mcpServers),
                  );
                }}
              >
                {t('settings.mcpLoadFour')}
              </button>
              <button
                type="button"
                className="btn-outline h-8 py-1 text-xs"
                disabled={!draft.mcpEnabled}
                onClick={() => {
                  applyMcpServers(
                    keepRecommendedMcpServers(parseMcpServersJson(mcpJson) ?? draft.mcpServers),
                  );
                }}
              >
                {t('settings.mcpCloseExtra')}
              </button>
              <button
                type="button"
                className="btn-outline h-8 py-1 text-xs"
                disabled={!draft.mcpEnabled}
                onClick={() => applyMcpServers(clearAllMcpServers())}
              >
                {t('settings.mcpCloseAll')}
              </button>
              <p className="text-[11.5px] text-slate-500">
                {(() => {
                  const count = (parseMcpServersJson(mcpJson) ?? draft.mcpServers).length;
                  const capNote =
                    count >= MCP_SERVERS_STORE_CAP
                      ? t('settings.mcp.capFull', { cap: MCP_SERVERS_STORE_CAP })
                      : '';
                  return `${t('settings.mcp.openCount', { count, cap: MCP_SERVERS_STORE_CAP })}${capNote}${t('settings.mcp.saveHint')}`;
                })()}
              </p>
            </div>
            <details className="rounded-lg border border-uryx-border bg-uryx-panel/30 px-3 py-2">
              <summary className="cursor-pointer text-[12.5px] font-medium text-slate-300">
                {t('settings.mcp.advanced')}
              </summary>
              <p className="mt-2 text-[11.5px] leading-relaxed text-slate-600">
                {t('settings.mcp.advancedHint')}
              </p>
              <textarea
                value={mcpJson}
                onChange={(event) => setMcpJson(event.target.value)}
                className="input mt-2 min-h-[140px] font-mono text-[12px]"
                disabled={!draft.mcpEnabled}
                spellCheck={false}
              />
              <p className="mt-1 text-[11.5px] text-slate-500">
                {(() => {
                  const state = describeMcpServersJson(mcpJson, language);
                  return state.ok
                    ? `${t('settings.mcp.jsonOk', { count: state.count })}${state.hint ? ` ${state.hint}` : ''}`
                    : state.error;
                })()}
              </p>
            </details>
          </Section>

          {/* Hafıza ve RAG */}
          <Section title={t('settings.section.memory')} filter={settingsQuery}>
            <Toggle
              checked={draft.autoMemoryEnabled}
              onChange={(value) => set('autoMemoryEnabled', value)}
              label={t('settings.autoMemory')}
              description={t('settings.autoMemoryDesc')}
            />
            <Toggle
              checked={draft.ragEnabled}
              onChange={(value) => set('ragEnabled', value)}
              label={t('settings.ragSearch')}
              description={t('settings.ragSearchDesc')}
            />
            <Field label={t('settings.ragTopK', { n: draft.ragTopK })}>
              <input
                type="range"
                min={1}
                max={20}
                step={1}
                value={draft.ragTopK}
                onChange={(event) => set('ragTopK', Number(event.target.value))}
                className="w-full accent-uryx-accent"
                disabled={!draft.ragEnabled}
              />
            </Field>
          </Section>

          {/* Uygulama */}
          <Section
            title={t('settings.section.app')}
            filter={settingsQuery}
            keywords="yeşil mavi tema renk arayüz accent palet dil language english türkçe açık koyu light dark sistem görünüm"
          >
            <Field
              label={t('settings.language')}
              hint={t('settings.languageHint')}
            >
              <div className="flex gap-2">
                <button
                  type="button"
                  className={cn('btn-outline', draft.language === 'tr' && 'ring-1 ring-uryx-accent')}
                  onClick={() => applyLanguage('tr')}
                >
                  {t('settings.lang.tr')}
                </button>
                <button
                  type="button"
                  className={cn('btn-outline', draft.language === 'en' && 'ring-1 ring-uryx-accent')}
                  onClick={() => applyLanguage('en')}
                >
                  {t('settings.lang.en')}
                </button>
              </div>
            </Field>
            <Field
              label={t('settings.accent')}
              hint={t('settings.accentHint')}
            >
              <AccentThemePicker
                value={draft.accentTheme}
                onChange={(accent) => {
                  set('accentTheme', accent);
                  void update({ accentTheme: accent });
                }}
              />
            </Field>
            <Field
              label={t('settings.shortcut')}
              hint={t('settings.shortcutHint')}
            >
              <input
                value={draft.globalShortcut}
                onChange={(event) => set('globalShortcut', event.target.value)}
                className="input font-mono"
              />
            </Field>
            <Field
              label={t('settings.ptt')}
              hint={t('settings.pttHint')}
            >
              <input
                value={draft.pushToTalkKey}
                onChange={(event) => set('pushToTalkKey', event.target.value)}
                className="input font-mono"
              />
            </Field>
            <Toggle
              checked={draft.launchOnStartup}
              onChange={(value) => set('launchOnStartup', value)}
              label={t('settings.launch')}
            />
            <Toggle
              checked={draft.minimizeToTray}
              onChange={(value) => set('minimizeToTray', value)}
              label={t('settings.trayMin')}
            />
            <Toggle
              checked={draft.closeToTray}
              onChange={(value) => set('closeToTray', value)}
              label={t('settings.trayClose')}
              description={t('settings.trayCloseDesc')}
            />
            <Toggle
              checked={draft.requireRiskConfirmation}
              onChange={(value) => set('requireRiskConfirmation', value)}
              label={t('settings.riskConfirm')}
              description={t('settings.riskConfirmDesc')}
            />
          </Section>

          {/* Hakkında */}
          <Section title={t('settings.section.about')} filter={settingsQuery}>
            <div className="card p-3">
              <InfoRow label={t('settings.about.version')} value={appInfo.data?.version ?? '—'} />
              <InfoRow label="Electron" value={appInfo.data?.electronVersion ?? '—'} />
              <InfoRow label="Chromium" value={appInfo.data?.chromeVersion ?? '—'} />
              <InfoRow label="Node" value={appInfo.data?.nodeVersion ?? '—'} />
              <InfoRow
                label={t('settings.about.settingsFile')}
                value={displaySafePath(appInfo.data?.userDataPath) || t('settings.about.missing')}
              />
            </div>
            {window.uryx && (
              <div className="flex items-center justify-between gap-3 rounded-lg border border-uryx-border bg-uryx-panel/40 px-3 py-2.5">
                <div className="min-w-0">
                  <p className="text-[13px] font-medium text-slate-200">{t('settings.about.update')}</p>
                  <p className="text-[12px] text-slate-500">
                    {t('settings.about.updateHint')}
                  </p>
                </div>
                <button
                  type="button"
                  className="btn-outline shrink-0"
                  disabled={checkingUpdate}
                  onClick={() => {
                    void (async () => {
                      setCheckingUpdate(true);
                      try {
                        const result = await window.uryx?.updater.check();
                        if (!result) {
                          pushToast('error', t('settings.about.updateMissing'));
                          return;
                        }
                        if (result.phase === 'available') {
                          pushToast('success', t('settings.about.updateReady', { version: result.version ?? '' }));
                        } else if (result.phase === 'error') {
                          pushToast('error', result.message ?? t('settings.about.updateFail'));
                        } else if (result.phase === 'idle' || result.phase === 'checking') {
                          pushToast('info', t('settings.about.upToDate'));
                        }
                      } catch (error) {
                        pushToast(
                          'error',
                          error instanceof Error ? error.message : t('settings.about.updateFail'),
                        );
                      } finally {
                        setCheckingUpdate(false);
                      }
                    })();
                  }}
                >
                  <RefreshCw size={14} className={checkingUpdate ? 'animate-spin' : undefined} />
                  {checkingUpdate ? t('settings.about.checking') : t('settings.about.checkUpdate')}
                </button>
              </div>
            )}
          </Section>
        </div>
      </div>
    </div>
  );
}

function Section({
  title,
  description,
  filter,
  keywords,
  children,
}: {
  title: string;
  description?: string;
  filter?: string;
  keywords?: string;
  children: React.ReactNode;
}): JSX.Element | null {
  const query = filter?.trim().toLocaleLowerCase('tr-TR') ?? '';
  const haystack = `${title} ${description ?? ''} ${keywords ?? ''}`.toLocaleLowerCase('tr-TR');
  if (query && !haystack.includes(query)) return null;

  return (
    <section className="panel p-4">
      <h2 className="text-sm font-semibold text-slate-100">{title}</h2>
      {description && (
        <p className="mt-0.5 min-w-0 text-[12px] leading-relaxed text-slate-500 [overflow-wrap:anywhere]">
          {description}
        </p>
      )}
      <div className="mt-3 space-y-3">{children}</div>
    </section>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <div>
      <label className="label">{label}</label>
      {children}
      {hint && (
        <p className="mt-1 min-w-0 text-[11.5px] leading-relaxed text-slate-600 [overflow-wrap:anywhere]">
          {hint}
        </p>
      )}
    </div>
  );
}

function mcpCopy(
  t: (key: MessageKey, vars?: Record<string, string | number>) => string,
  key: string,
  fallback: string,
): string {
  return key in MESSAGE_TABLES.en ? t(key as MessageKey) : fallback;
}

function McpRecipeGroup({
  t,
  title,
  cards,
  servers,
  disabled,
  groupActive,
  onGroupToggle,
  onToggle,
  onEnv,
}: {
  t: (key: MessageKey, vars?: Record<string, string | number>) => string;
  title: string;
  cards: readonly McpRecipeMeta[];
  servers: McpServerConfig[];
  disabled: boolean;
  groupActive: boolean;
  onGroupToggle: (enabled: boolean) => void;
  onToggle: (id: string, enabled: boolean) => void;
  onEnv: (id: string, key: string, value: string) => void;
}): JSX.Element {
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[11.5px] font-medium uppercase tracking-wide text-slate-500">{title}</p>
        <button
          type="button"
          className="btn-outline h-8 py-1 text-xs"
          disabled={disabled}
          onClick={() => onGroupToggle(!groupActive)}
          aria-label={
            groupActive
              ? t('settings.mcp.groupOffAria', { title })
              : t('settings.mcp.groupOnAria', { title })
          }
        >
          {groupActive ? t('settings.mcp.groupOff') : t('settings.mcp.groupOn')}
        </button>
      </div>
      {cards.map((card) => {
        const enabled = hasMcpServer(servers, card.id);
        const env = servers.find((server) => server.id === card.id)?.env ?? {};
        const overlap = mcpCopy(t, `mcp.overlap.${card.id}`, mcpNativeOverlapNote(card.id) ?? '');
        return (
          <div
            key={card.id}
            className="rounded-lg border border-uryx-border bg-uryx-panel/40 px-3 py-2"
          >
            <Toggle
              checked={enabled}
              onChange={(value) => onToggle(card.id, value)}
              label={`${mcpCopy(t, `mcp.${card.id}.title`, card.title)} (${card.runtime})`}
              description={mcpCopy(t, `mcp.${card.id}.desc`, card.description)}
              disabled={disabled}
            />
            {overlap && (
              <p className="mt-1 text-[11.5px] leading-relaxed text-slate-600">{overlap}</p>
            )}
            {enabled &&
              card.env?.map((field) => (
                <div key={field.key} className="mt-2 pl-0.5">
                  <label className="label">
                    {mcpCopy(t, `mcp.env.${field.key}.label`, field.label)}
                  </label>
                  <SecretInput
                    value={env[field.key] ?? ''}
                    onChange={(value) => onEnv(card.id, field.key, value)}
                    placeholder={t('settings.mcp.envStored')}
                  />
                  <p className="mt-1 text-[11.5px] leading-relaxed text-slate-600">
                    {mcpCopy(t, `mcp.env.${field.key}.hint`, field.hint ?? '')}
                  </p>
                </div>
              ))}
          </div>
        );
      })}
    </div>
  );
}

