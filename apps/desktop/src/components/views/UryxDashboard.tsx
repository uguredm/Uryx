import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import {
  Archive,
  Brain,
  ChevronsDown,
  Database,
  File,
  FileText,
  Film,
  Images,
  Mic,
  Play,
  Plus,
  Power,
  Settings,
  Copy,
  Download,
  Pin,
  Quote,
  RefreshCw,
  Square,
  Terminal,
  Volume2,
  VolumeX,
  Wrench,
  X,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { Composer } from '@/components/chat/Composer';
import { MessageCollapse } from '@/components/chat/MessageCollapse';
import { MarkdownImage, MarkdownPre, safeMarkdownUrl } from '@/components/chat/MessageBubble';
import { AccentThemePicker } from '@/components/common/AccentThemePicker';
import { HudHealthChip } from '@/components/hud/HudHealthChip';
import { HudHashEmbed } from '@/components/hud/HudHashEmbed';
import { UryxCoreCanvas, type UryxCoreState } from '@/components/hud/UryxCoreCanvas';
import { HudTerminalOptions } from '@/components/hud/HudTerminalOptions';
import { useSystemStore } from '@/hooks/useSystemStatus';
import {
  hudMessagePlainText,
  hudToolLabel,
  HUD_TOOL_STATUS_KEYS,
  quoteMessageText,
  shouldShowStreamingBubble,
  summarizedToolStatus,
} from '@/lib/confirmResponse';
import { cn } from '@/lib/cn';
import {
  canExportConversation,
  exportConversationMarkdown,
  titleFromMessages,
} from '@/lib/exportConversation';
import { copyPlainText } from '@/lib/historySearch';
import {
  formatFindCount,
  matchFindShortcut,
  matchingMessageIds,
  wrapFindIndex,
} from '@/lib/hudFind';
import { useI18n, type MessageKey } from '@/lib/i18n';
import { serviceDisplayName, toolDisplayName, localizeApiText } from '@/lib/apiText';
import { formatDecimal } from '@/lib/format';
import { HUD_COLLAPSE_MAX_PX } from '@/lib/messageCollapse';
import { stampFromIso } from '@/lib/relativeStamp';
import { canRetryLastTurn, chatTurnOptions, lastUserPrompt } from '@/lib/retryLastTurn';
import { isNearBottom, lastCopyableText, shouldAutoScroll } from '@/lib/scrollStick';
import { usePinnedChatsStore } from '@/lib/pinnedChats';
import { useChatStore } from '@/stores/chatStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { quoteToComposer, type ViewName, useUIStore } from '@/stores/uiStore';

const STATE_KEYS: Record<UryxCoreState, MessageKey> = {
  ready: 'hud.state.ready',
  offline: 'hud.state.offline',
  listening: 'hud.state.listening',
  transcribing: 'hud.state.transcribing',
  thinking: 'hud.state.thinking',
  speaking: 'hud.state.speaking',
  error: 'hud.state.error',
};

const NAV_ITEMS: Array<{ view: ViewName; labelKey: MessageKey; icon: typeof Archive }> = [
  { view: 'history', labelKey: 'hud.nav.history', icon: Archive },
  { view: 'memory', labelKey: 'hud.nav.memory', icon: Brain },
  { view: 'documents', labelKey: 'hud.nav.documents', icon: FileText },
  { view: 'tools', labelKey: 'hud.nav.tools', icon: Wrench },
  { view: 'system', labelKey: 'hud.nav.system', icon: Database },
  { view: 'settings', labelKey: 'hud.nav.settings', icon: Settings },
];

export function UryxDashboard(): JSX.Element {
  const [now, setNow] = useState(() => new Date());
  const [dismissedArtifactId, setDismissedArtifactId] = useState<string | null>(null);
  const [hudFind, setHudFind] = useState('');
  const [findIndex, setFindIndex] = useState(-1);
  const [stickToBottom, setStickToBottom] = useState(true);
  const pinnedIds = usePinnedChatsStore((state) => state.ids);
  const togglePin = usePinnedChatsStore((state) => state.toggle);
  const logRef = useRef<HTMLDivElement>(null);
  const findInputRef = useRef<HTMLInputElement>(null);
  const status = useSystemStore((state) => state.status);
  const systemConnected = useSystemStore((state) => state.connected);
  const settings = useSettingsStore((state) => state.settings);
  const updateSettings = useSettingsStore((state) => state.update);
  const { t, locale, language } = useI18n();
  const setView = useUIStore((state) => state.setView);
  const voiceState = useUIStore((state) => state.voiceState);
  const voiceLevel = useUIStore((state) => state.voiceLevel);
  const requestVoiceToggle = useUIStore((state) => state.requestVoiceToggle);
  const pushToast = useUIStore((state) => state.pushToast);
  const sttPartial = useUIStore((state) => state.sttPartial);
  const {
    messages,
    conversationId,
    generating,
    streamContent,
    streamThinking,
    liveToolCalls,
    connection,
    speaking,
    ttsError,
    newConversation,
    sendMessage,
    stopSpeech,
    cancel,
    streamDropped,
  } = useChatStore();

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const element = logRef.current;
    if (element && shouldAutoScroll(stickToBottom)) {
      element.scrollTop = element.scrollHeight;
    }
  }, [messages.length, streamContent, streamThinking, liveToolCalls, stickToBottom]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (!(event.ctrlKey || event.metaKey) || !event.shiftKey || event.key.toLowerCase() !== 'c') {
        return;
      }
      const target = event.target as HTMLElement | null;
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA')) return;
      const text = lastCopyableText(messages);
      if (!text) return;
      event.preventDefault();
      void navigator.clipboard.writeText(text).then(
        () => pushToast('success', t('toast.copyLast')),
        () => pushToast('error', t('toast.copyFail')),
      );
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [messages, pushToast]);

  const findMatchIds = useMemo(
    () => matchingMessageIds(messages, hudFind),
    [messages, hudFind],
  );
  const currentFindId = findIndex >= 0 ? findMatchIds[findIndex] : undefined;

  useEffect(() => {
    setFindIndex(findMatchIds.length ? 0 : -1);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- findMatchIds yalnızca bu iki tetikte
  }, [hudFind, conversationId]);

  useEffect(() => {
    setFindIndex((current) => {
      if (findMatchIds.length === 0) return -1;
      if (current < 0 || current >= findMatchIds.length) return 0;
      return current;
    });
  }, [findMatchIds]);

  useEffect(() => {
    if (findIndex < 0 || !currentFindId) return;
    const root = logRef.current;
    if (!root) return;
    const escaped =
      typeof CSS !== 'undefined' && typeof CSS.escape === 'function'
        ? CSS.escape(currentFindId)
        : currentFindId.replace(/"/g, '');
    const element = root.querySelector(`[data-find-id="${escaped}"]`);
    if (!(element instanceof HTMLElement)) return;
    setStickToBottom(false);
    element.scrollIntoView({ block: 'center' });
  }, [findIndex, currentFindId]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (useUIStore.getState().view !== 'chat') return;
      const findFocused = findInputRef.current === document.activeElement;
      const shortcut = matchFindShortcut(event, findFocused);
      if (!shortcut) return;
      if (shortcut === 'openFind') {
        event.preventDefault();
        findInputRef.current?.focus();
        findInputRef.current?.select();
        return;
      }
      if (shortcut === 'clearFind') {
        event.preventDefault();
        setHudFind('');
        return;
      }
      if (!hudFind.trim()) {
        event.preventDefault();
        findInputRef.current?.focus();
        return;
      }
      event.preventDefault();
      setStickToBottom(false);
      setFindIndex((current) =>
        wrapFindIndex(current, shortcut === 'findNext' ? 1 : -1, findMatchIds.length),
      );
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [hudFind, findMatchIds.length]);

  const coreState: UryxCoreState =
    voiceState === 'listening'
      ? 'listening'
      : voiceState === 'transcribing'
        ? 'transcribing'
        : generating
          ? 'thinking'
          : speaking
            ? 'speaking'
            : connection === 'open'
              ? 'ready'
              : 'offline';

  const timestamp = useMemo(
    () => ({
      time: now.toLocaleTimeString(locale, {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      }),
      date: now.toLocaleDateString(locale, { day: '2-digit', month: '2-digit', year: 'numeric' }),
      day: now.toLocaleDateString(locale, { weekday: 'long' }).toLocaleUpperCase(locale),
    }),
    [now, locale],
  );
  const metrics = status?.metrics;
  const onlineServices = status?.services.filter((service) => service.state === 'up').length ?? 0;
  const serviceCount = status?.services.length ?? 0;
  const artifact = useMemo(
    () => findLatestArtifact(messages, liveToolCalls, t),
    [messages, liveToolCalls, t],
  );
  const showArtifact = artifact && artifact.id !== dismissedArtifactId;

  return (
    <div className="uryx-dashboard">
      <header className="uryx-dashboard__header">
        <div className="hud-brand">
          <span className="hud-brand__mark">U</span>
          <div>
            <strong>URYX</strong>
            <span>{t('hud.brand.sub')}</span>
          </div>
        </div>
        <div className="hud-header-channel">
          <span>{t('hud.header.channel')}</span>
          <strong title={status?.model.model_id ?? settings.modelName}>
            {status?.model.model_id ?? settings.modelName}
          </strong>
        </div>
        <div className="hud-header-clock">
          <HudHealthChip />
          <AccentThemePicker
            variant="hud"
            value={settings.accentTheme}
            onChange={(accent) => {
              void updateSettings({ accentTheme: accent });
            }}
          />
          <span>
            {timestamp.day}
            {' // '}
            {timestamp.date}
          </span>
        </div>
      </header>

      <aside className="uryx-dashboard__left">
        <HudSection title={t('hud.section.time')} code="01">
          <div className="hud-time">{timestamp.time}</div>
          <div className="hud-muted">{t('hud.istanbul')}</div>
        </HudSection>

        <HudSection title={t('hud.section.status')} code="02">
          <Metric
            label={t('hud.metric.cpu')}
            value={metrics?.cpu_percent}
            detail={metrics ? t('hud.metric.cores', { n: metrics.cpu_cores }) : undefined}
          />
          <Metric
            label={t('hud.metric.memory')}
            value={metrics?.ram_percent}
            detail={
              metrics
                ? `${toGb(metrics.ram_used_mb, language)} / ${toGb(metrics.ram_total_mb, language)} GB`
                : undefined
            }
          />
          {metrics?.gpu.available && (
            <>
              <Metric label={t('hud.metric.gpu')} value={metrics.gpu.utilization_percent} />
              <Metric
                label={t('hud.metric.vram')}
                value={metrics.gpu.vram_percent}
                detail={`${toGb(metrics.gpu.vram_used_mb, language)} / ${toGb(metrics.gpu.vram_total_mb, language)} GB`}
                warn
              />
            </>
          )}
          <div className="hud-system-detail">
            <span>{metrics?.gpu.available ? metrics.gpu.name : t('hud.gpu.pending')}</span>
            <strong>{metrics?.gpu.temperature_c ? `${metrics.gpu.temperature_c} C` : '--'}</strong>
          </div>
          <HudHashEmbed />
        </HudSection>

        <HudSection title={t('hud.section.services')} code="03" grow>
          <div className="hud-service-summary">
            <strong>{onlineServices.toString().padStart(2, '0')}</strong>
            <span>
              / {serviceCount.toString().padStart(2, '0')} {t('hud.services.online')}
            </span>
          </div>
          <div className="hud-services">
            {(status?.services ?? []).slice(0, 7).map((service) => (
              <div key={service.name} className="hud-service-row">
                <span className={cn('hud-status-dot', `is-${service.state}`)} />
                <span>
                  {serviceDisplayName(service.name, service.display_name, language).toLocaleUpperCase(locale)}
                </span>
                <strong>
                  {t(
                    service.state === 'up'
                      ? 'hud.service.up'
                      : service.state === 'down'
                        ? 'hud.service.down'
                        : service.state === 'degraded'
                          ? 'hud.service.degraded'
                          : service.state === 'starting'
                            ? 'hud.service.starting'
                            : 'hud.service.unknown',
                  )}
                </strong>
              </div>
            ))}
            {!status && <div className="hud-muted">{t('hud.services.wait')}</div>}
          </div>
        </HudSection>

        <nav className="hud-nav" aria-label="Uryx">
          {NAV_ITEMS.map(({ view, labelKey, icon: Icon }) => (
            <button key={view} type="button" onClick={() => setView(view)} title={t(labelKey)}>
              <Icon size={13} />
              <span>{t(labelKey)}</span>
            </button>
          ))}
        </nav>
      </aside>

      <main className="uryx-dashboard__center">
        <div className="hud-center-grid" aria-hidden />
        {showArtifact ? (
          <HudArtifactStage
            artifact={artifact}
            t={t}
            onClose={() => setDismissedArtifactId(artifact.id)}
          />
        ) : (
          <>
            <div className="hud-core-callout hud-core-callout--left">
              <span>{t('hud.callout.voice')}</span>
              <strong>{voiceState === 'idle' ? t('hud.standby') : t('hud.active')}</strong>
            </div>
            <div className="hud-core-callout hud-core-callout--right">
              <span>{t('hud.callout.process')}</span>
              <strong>{t(STATE_KEYS[coreState])}</strong>
            </div>
            <div className="hud-core-wrap">
              <UryxCoreCanvas
                state={coreState}
                level={voiceLevel}
                onActivate={requestVoiceToggle}
              />
            </div>
            <div className="hud-core-identity">
              <span>{t(STATE_KEYS[coreState])}</span>
              <h1>U.R.Y.X</h1>
              <p>{sttPartial || t('hud.identity.idle')}</p>
            </div>
          </>
        )}
        <div className="hud-core-controls">
          <HudControl
            icon={<Mic size={15} />}
            label={voiceState === 'listening' ? t('hud.control.listen') : t('hud.control.voice')}
            active={voiceState !== 'idle'}
            onClick={requestVoiceToggle}
          />
          <HudControl
            icon={settings.ttsEnabled ? <Volume2 size={15} /> : <VolumeX size={15} />}
            label={settings.ttsEnabled ? t('hud.control.audioOn') : t('hud.control.audioOff')}
            active={settings.ttsEnabled}
            onClick={() => {
              if (speaking) stopSpeech();
              void updateSettings({ ttsEnabled: !settings.ttsEnabled });
            }}
          />
          <HudControl
            icon={generating ? <Square size={14} /> : <Plus size={15} />}
            label={generating ? t('hud.control.abort') : t('hud.control.new')}
            alert={generating}
            onClick={generating ? cancel : newConversation}
          />
          <HudControl
            icon={<Settings size={15} />}
            label={t('hud.control.config')}
            onClick={() => setView('settings')}
          />
        </div>
      </main>

      <aside className="uryx-dashboard__terminal">
        <div className="hud-terminal-header">
          <div>
            <Terminal size={14} />
            <span>{t('hud.terminal.title')}</span>
          </div>
          <label className="hud-terminal-find-wrap">
            <input
              ref={findInputRef}
              value={hudFind}
              onChange={(event) => setHudFind(event.target.value)}
              placeholder={t('hud.terminal.find')}
              className="hud-terminal-find"
              aria-label={t('hud.terminal.find')}
            />
            {hudFind.trim() ? (
              <span className="hud-terminal-find-count" aria-live="polite">
                {formatFindCount(findIndex, findMatchIds.length)}
              </span>
            ) : null}
          </label>
          {canExportConversation(messages) && (
            <button
              type="button"
              className="hud-log-copy"
              aria-label={t('hud.action.exportMd')}
              title={t('hud.action.exportMd')}
              onClick={() => {
                void exportConversationMarkdown({
                  title: titleFromMessages(messages),
                  messages,
                }).then((ok) => {
                  pushToast(ok ? 'success' : 'warning', ok ? t('toast.exportOk') : t('toast.exportEmpty'));
                });
              }}
            >
              <Download size={12} />
            </button>
          )}
          {conversationId && (
            <button
              type="button"
              className="hud-log-copy"
              aria-label={pinnedIds.includes(conversationId) ? t('hud.action.unpin') : t('hud.action.pinChat')}
              title={pinnedIds.includes(conversationId) ? t('hud.action.unpin') : t('hud.action.pinChat')}
              onClick={() => togglePin(conversationId)}
            >
              <Pin size={12} />
            </button>
          )}
          {generating ? (
            <button type="button" className="hud-stream-stop" onClick={cancel}>
              {t('hud.control.abort')}
            </button>
          ) : (
            <strong className={connection === 'open' ? 'is-online' : ''}>
              {connection === 'open' ? t('hud.terminal.linked') : t('hud.terminal.offline')}
            </strong>
          )}
        </div>
        {streamDropped && (
          <div className="hud-stream-dropped" role="status">
            {t('hud.stream.dropped')}
          </div>
        )}
        <div className="hud-terminal-log-wrap">
        <div
          ref={logRef}
          className="hud-terminal-log scroll-area"
          onScroll={() => {
            const element = logRef.current;
            if (!element) return;
            setStickToBottom(isNearBottom(element));
          }}
        >
          {messages.length === 0 && !generating && (
            <div className="hud-terminal-boot">
              <Power size={18} />
              <p>{t('hud.boot.title')}</p>
              <span>{t('hud.boot.sub')}</span>
            </div>
          )}
          {messages.map((message) => (
            <article
              key={message.id}
              data-find-id={message.id}
              className={cn(
                'hud-log-entry',
                `is-${message.role}`,
                hudFind.trim() && findMatchIds.includes(message.id) && 'is-hit',
                hudFind.trim() && !findMatchIds.includes(message.id) && 'is-dim',
                currentFindId === message.id && 'is-find-current',
              )}
            >
              <header>
                <span>{message.role === 'user' ? t('hud.role.user') : 'URYX'}</span>
                <div className="hud-log-actions">
                  <time dateTime={message.createdAt} title={stampFromIso(message.createdAt, now, language).title}>
                    {stampFromIso(message.createdAt, now, language).label}
                  </time>
                  <button
                    type="button"
                    className="hud-log-copy"
                    aria-label={t('hud.action.copyLine')}
                    title={t('hud.action.copyLine')}
                    onClick={() => {
                      const text = copyPlainText(
                        hudMessagePlainText(
                          stripArtifactMarkup(message.content || message.error || ''),
                          message.toolCalls,
                        ),
                      );
                      if (!text) {
                        pushToast('warning', t('toast.copyEmpty'));
                        return;
                      }
                      void navigator.clipboard.writeText(text).then(
                        () => pushToast('success', t('toast.copyOk')),
                        () => pushToast('error', t('toast.copyFail')),
                      );
                    }}
                  >
                    <Copy size={10} />
                  </button>
                  <button
                    type="button"
                    className="hud-log-copy"
                    aria-label={t('hud.action.quote')}
                    title={t('hud.action.quote')}
                    onClick={() => {
                      const text = quoteMessageText(
                        stripArtifactMarkup(message.content || message.error || ''),
                        message.toolCalls,
                      );
                      if (!quoteToComposer(text)) {
                        pushToast('warning', t('toast.quoteEmpty'));
                      }
                    }}
                  >
                    <Quote size={10} />
                  </button>
                  {canRetryLastTurn({ generating, messages }) &&
                    message.id === messages[messages.length - 1]?.id && (
                      <button
                        type="button"
                        className="hud-log-copy"
                        aria-label={t('hud.action.retryLast')}
                        title={t('hud.action.retry')}
                        onClick={() => {
                          const prompt = lastUserPrompt(messages);
                          if (!prompt || !sendMessage(prompt, chatTurnOptions(settings))) {
                            pushToast('warning', t('toast.retryEmpty'));
                            return;
                          }
                          pushToast('success', t('toast.retryOk'));
                        }}
                      >
                        <RefreshCw size={10} />
                      </button>
                    )}
                </div>
              </header>
              {message.thinking && (
                <details>
                  <summary>{t('hud.thinking')}</summary>
                  <p>{message.thinking}</p>
                </details>
              )}
              {(message.toolCalls ?? []).map((call, index) => (
                <div key={`${call.tool_name}-${index}`} className="hud-tool-line">
                  <Wrench size={11} />
                  <span>
                    {hudToolLabel(
                      call.tool_name,
                      toolDisplayName(call.tool_name, call.display_name ?? call.tool_name, language),
                      call.arguments,
                      call.result,
                    ).toLocaleUpperCase(locale)}
                  </span>
                  <strong>
                    {t(HUD_TOOL_STATUS_KEYS[summarizedToolStatus(call.tool_name, call)])}
                  </strong>
                </div>
              ))}
              <MessageCollapse
                contentKey={message.id + (message.content || message.error || '')}
                maxHeight={HUD_COLLAPSE_MAX_PX}
                buttonClassName="hud-show-more"
              >
                {message.role === 'assistant' ? (
                  <div className="markdown hud-terminal-markdown">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{ img: MarkdownImage, pre: MarkdownPre }}
                      urlTransform={safeMarkdownUrl}
                    >
                      {stripArtifactMarkup(message.content || message.error || '')}
                    </ReactMarkdown>
                  </div>
                ) : (
                  <p>{message.content || message.error}</p>
                )}
              </MessageCollapse>
              {message.stopped && <div className="hud-log-stopped">{t('hud.stopped')}</div>}
              {message.error && (
                <div className="hud-log-error">
                  {t('hud.error', { msg: localizeApiText(message.error, language) || message.error })}
                </div>
              )}
            </article>
          ))}
          {liveToolCalls.map((call) => (
            <div key={call.callId} className="hud-tool-line">
              <Wrench size={11} />
              <span>
                {hudToolLabel(
                  call.toolName,
                  toolDisplayName(call.toolName, call.displayName, language),
                  call.arguments,
                  call.result,
                ).toLocaleUpperCase(locale)}
              </span>
              <strong>
                {t(
                  HUD_TOOL_STATUS_KEYS[
                    summarizedToolStatus(call.toolName, {
                      status: call.status,
                      error: call.error,
                      result: call.result,
                    })
                  ],
                )}
              </strong>
            </div>
          ))}
          {generating && shouldShowStreamingBubble(streamContent, streamThinking) && (
            <article className="hud-log-entry is-assistant is-streaming">
              <header>
                <span>URYX</span>
                <strong>{t('hud.processing')}</strong>
              </header>
              {streamThinking && (
                <details>
                  <summary>{t('hud.thinking')}</summary>
                  <p>{streamThinking}</p>
                </details>
              )}
              <div className="markdown hud-terminal-markdown">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{ img: MarkdownImage, pre: MarkdownPre }}
                  urlTransform={safeMarkdownUrl}
                >
                  {streamContent}
                </ReactMarkdown>
                <span className="hud-cursor" />
              </div>
            </article>
          )}
          {ttsError && <div className="hud-log-error">{t('hud.voiceError', { msg: ttsError })}</div>}
        </div>
        {!stickToBottom && (
          <button
            type="button"
            className="hud-scroll-bottom"
            onClick={() => {
              setStickToBottom(true);
              const element = logRef.current;
              if (element) element.scrollTop = element.scrollHeight;
            }}
            aria-label={t('hud.action.scrollBottom')}
            title={t('hud.action.scrollBottom')}
          >
            <ChevronsDown size={14} />
            {t('hud.scrollBottom')}
          </button>
        )}
        </div>
        <HudTerminalOptions
          settings={settings}
          onUpdate={updateSettings}
          stopSpeech={stopSpeech}
        />
        <Composer variant="hud" />
      </aside>

      <footer className="uryx-dashboard__footer">
        <span>{t('hud.footer.ptt')}</span>
        <span>{t('hud.footer.channel')}</span>
        <strong className={systemConnected ? 'is-online' : ''}>
          {t('ws.footer.sys', {
            state: systemConnected ? t('hud.footer.online') : t('hud.footer.reconnect'),
          })}
        </strong>
      </footer>
    </div>
  );
}

function HudSection({
  title,
  code,
  grow,
  children,
}: {
  title: string;
  code: string;
  grow?: boolean;
  children: ReactNode;
}): JSX.Element {
  return (
    <section className={cn('hud-section', grow && 'hud-section--grow')}>
      <header>
        <span>{title}</span>
        <strong>{code}</strong>
      </header>
      <div className="hud-section__body">{children}</div>
    </section>
  );
}

function Metric({
  label,
  value,
  detail,
  warn,
}: {
  label: string;
  value?: number;
  detail?: string;
  warn?: boolean;
}): JSX.Element {
  const safeValue = Math.max(0, Math.min(100, value ?? 0));
  return (
    <div className="hud-metric">
      <div>
        <span>{label}</span>
        <strong>
          {value === undefined ? '--' : `${value.toFixed(0)}%`}
          {detail ? ` // ${detail}` : ''}
        </strong>
      </div>
      <div className={cn('hud-metric__track', warn && safeValue > 85 && 'is-warn')}>
        <i style={{ width: `${safeValue}%` }} />
      </div>
    </div>
  );
}

function HudControl({
  icon,
  label,
  active,
  alert,
  onClick,
}: {
  icon: JSX.Element;
  label: string;
  active?: boolean;
  alert?: boolean;
  onClick: () => void;
}): JSX.Element {
  return (
    <button
      type="button"
      className={cn(active && 'is-active', alert && 'is-alert')}
      onClick={onClick}
    >
      {icon}
      <span>{label}</span>
    </button>
  );
}

function toGb(megabytes: number, language: 'tr' | 'en'): string {
  return formatDecimal((megabytes / 1024).toFixed(1), language);
}

interface HudArtifact {
  id: string;
  images: Array<{ url: string; label: string }>;
  videos: Array<{ url: string; label: string; thumbnail?: string }>;
  documents: Array<{ label: string; detail: string; url?: string }>;
}

type Translate = (key: MessageKey, vars?: Record<string, string | number>) => string;

function matchDetail(t: Translate, page: unknown, score: number): string {
  const pct = (Number(score) * 100).toFixed(0);
  return typeof page === 'number'
    ? t('hud.artifact.pageMatch', { page, pct })
    : t('hud.artifact.match', { pct });
}

function findLatestArtifact(
  messages: ReturnType<typeof useChatStore.getState>['messages'],
  toolCalls: ReturnType<typeof useChatStore.getState>['liveToolCalls'],
  t: Translate,
): HudArtifact | null {
  for (let index = toolCalls.length - 1; index >= 0; index -= 1) {
    const call = toolCalls[index];
    const rawImages = call?.result?.images;
    const rawVideos = call?.result?.videos;
    if (!call) continue;
    const images = (Array.isArray(rawImages) ? rawImages : []).flatMap((item) => {
      if (!item || typeof item !== 'object') return [];
      const row = item as Record<string, unknown>;
      const url = toolImageUrl(row);
      if (!url) return [];
      return [{ url, label: String(row.title ?? t('hud.artifact.visual')) }];
    });
    const videos = extractToolVideos(rawVideos, t);
    const documents = extractSearchDocuments(call.result, t);
    if (images.length || videos.length || documents.length) {
      return { id: call.callId, images, videos, documents };
    }
  }

  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (!message || message.role !== 'assistant') continue;
    const toolImages = (message.toolCalls ?? []).flatMap((call) => {
      const rawImages = call.result?.images;
      if (!Array.isArray(rawImages)) return [];
      return rawImages.flatMap((item) => {
        if (!item || typeof item !== 'object') return [];
        const row = item as Record<string, unknown>;
        const url = toolImageUrl(row);
        if (!url) return [];
        return [{ url, label: String(row.title ?? t('hud.artifact.visual')) }];
      });
    });
    const toolVideos = (message.toolCalls ?? []).flatMap((call) =>
      extractToolVideos(call.result?.videos, t),
    );
    const markdownImages = [
      ...message.content.matchAll(/!\[([^\]]*)\]\((https:\/\/[^)]+)\)/gi),
    ].map((match) => ({ url: match[2]!, label: match[1] || t('hud.artifact.visual') }));
    const directImages = [
      ...message.content.matchAll(/https:\/\/[^\s)\]]+\.(?:jpe?g|png|webp|gif)(?:\?[^\s)\]]*)?/gi),
    ].map((match) => ({ url: match[0], label: t('hud.artifact.visual') }));
    const images = uniqueMedia([...toolImages, ...markdownImages, ...directImages]);
    const markdownVideos = [
      ...message.content.matchAll(
        /\[([^\]]+)\]\((https:\/\/(?:[^)]*?(?:youtube\.com\/watch\?[^)]*v=|youtu\.be\/|vimeo\.com\/)[^)]+|[^)]+\.(?:mp4|webm|mov)(?:\?[^)]*)?))\)/gi,
      ),
    ].map((match) => ({
      url: match[2]!,
      label: match[1] || t('hud.artifact.video'),
      thumbnail: youtubeThumbnail(match[2]!),
    }));
    const videos = [...toolVideos, ...markdownVideos];
    const sourceDocuments = (message.sources ?? [])
      .filter((source) => source.score >= 0.35)
      .map((source) => ({
      label: source.filename,
      detail: matchDetail(t, source.page, source.score),
    }));
    const linkedDocuments = [
      ...message.content.matchAll(
        /\[([^\]]+)\]\((https:\/\/[^)]+\.(?:pdf|docx?|xlsx?|pptx?|txt|csv)(?:\?[^)]*)?)\)/gi,
      ),
    ].map((match) => ({ label: match[1]!, detail: t('hud.artifact.remote'), url: match[2]! }));
    const toolDocuments = (message.toolCalls ?? []).flatMap((call) =>
      extractSearchDocuments(call.result, t),
    );
    const documents = [...sourceDocuments, ...toolDocuments, ...linkedDocuments];
    if (images.length || videos.length || documents.length) {
      return { id: message.id, images, videos, documents };
    }
  }
  return null;
}

function youtubeThumbnail(url: string): string | undefined {
  try {
    const parsed = new URL(url);
    const videoId = parsed.hostname.includes('youtu.be')
      ? parsed.pathname.split('/').filter(Boolean)[0]
      : parsed.searchParams.get('v');
    return videoId ? `https://img.youtube.com/vi/${videoId}/hqdefault.jpg` : undefined;
  } catch {
    return undefined;
  }
}

function extractSearchDocuments(raw: unknown, t: Translate): HudArtifact['documents'] {
  if (!raw || typeof raw !== 'object') return [];
  const results = (raw as Record<string, unknown>).results;
  if (!Array.isArray(results)) return [];
  return results.flatMap((item) => {
    if (!item || typeof item !== 'object') return [];
    const row = item as Record<string, unknown>;
    const label = String(row.filename ?? '').trim();
    if (!label) return [];
    return [{ label, detail: matchDetail(t, row.page, Number(row.score ?? 0)) }];
  });
}

function extractToolVideos(raw: unknown, t: Translate): HudArtifact['videos'] {
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((item) => {
    if (!item || typeof item !== 'object') return [];
    const row = item as Record<string, unknown>;
    const url = String(row.url ?? '');
    if (!/^https:\/\//i.test(url)) return [];
    return [
      {
        url,
        label: String(row.title ?? t('hud.artifact.video')),
        thumbnail: String(row.thumbnail ?? '') || youtubeThumbnail(url),
      },
    ];
  });
}

function uniqueMedia(
  items: Array<{ url: string; label: string }>,
): Array<{ url: string; label: string }> {
  return [...new Map(items.map((item) => [item.url, item])).values()].slice(0, 8);
}

function toolImageUrl(row: Record<string, unknown>): string {
  const remote = String(row.image ?? row.url ?? row.thumbnail ?? '');
  if (/^https:\/\//i.test(remote)) return remote;
  const filePath = String(row.path ?? '');
  return filePath ? `uryx-media://local/?path=${encodeURIComponent(filePath)}` : '';
}

function stripArtifactMarkup(content: string): string {
  return content
    .replace(/!\[[^\]]*\]\([^)]+\)/gi, '')
    .replace(/^\s*[*_-]*\s*(?:Kaynak|Görsel|Fotoğraf)\s*:.*$/gim, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function HudArtifactStage({
  artifact,
  t,
  onClose,
}: {
  artifact: HudArtifact;
  t: Translate;
  onClose: () => void;
}): JSX.Element {
  const [selectedImage, setSelectedImage] = useState(0);
  return (
    <section className="hud-artifact-stage">
      <header>
        <div>
          <Images size={14} />
          <span>{t('hud.artifact.title')}</span>
        </div>
        <strong>
          {String(
            artifact.images.length + artifact.videos.length + artifact.documents.length,
          ).padStart(2, '0')}{' '}
          {t('hud.artifact.objects')}
        </strong>
        <button
          type="button"
          onClick={onClose}
          title={t('hud.artifact.close')}
          aria-label={t('hud.artifact.close')}
        >
          <X size={15} />
        </button>
      </header>
      <div className="hud-artifact-stage__body">
        {artifact.images.length > 0 && (
          <div className="hud-artifact-visual">
            <MarkdownImage
              src={artifact.images[selectedImage]?.url}
              alt={artifact.images[selectedImage]?.label}
            />
            {artifact.images.length > 1 && (
              <div className="hud-artifact-thumbs">
                {artifact.images.slice(0, 8).map((item, index) => (
                  <button
                    key={item.url}
                    type="button"
                    className={index === selectedImage ? 'is-active' : ''}
                    onClick={() => setSelectedImage(index)}
                  >
                    <img src={item.url} alt={item.label} />
                    <span>{String(index + 1).padStart(2, '0')}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
        {artifact.videos.map((video) => (
          <div key={video.url} className="hud-artifact-video">
            <div>
              <Film size={12} /> {t('hud.artifact.video')} {video.label}
            </div>
            {video.thumbnail ? (
              <a href={video.url} target="_blank" rel="noreferrer">
                <img src={video.thumbnail} alt={video.label} />
                <span>
                  <Play size={24} /> {t('hud.artifact.openVideo')}
                </span>
              </a>
            ) : (
              <video src={video.url} controls preload="metadata" />
            )}
          </div>
        ))}
        {artifact.documents.length > 0 && (
          <div className="hud-artifact-documents">
            <div className="hud-artifact-label">
              <File size={12} /> {t('hud.artifact.docs')}
            </div>
            {artifact.documents.map((document) => (
              <div key={`${document.label}-${document.detail}`}>
                <FileText size={13} />
                <span>{document.label}</span>
                {document.url ? (
                  <a href={document.url} target="_blank" rel="noreferrer">
                    {t('hud.artifact.openFile')}
                  </a>
                ) : (
                  <strong>{document.detail}</strong>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
