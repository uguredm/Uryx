/** Tek bir sohbet mesajı (markdown, kod blokları, kaynaklar, araçlar). */

import { memo, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import ReactMarkdown from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import remarkGfm from 'remark-gfm';
import { AlertCircle, Brain, Check, Copy, Maximize2, Quote, RefreshCw, User, Volume2, X } from 'lucide-react';

import { cn } from '@/lib/cn';
import { hudMessagePlainText, quoteMessageText, summarizedToolStatus } from '@/lib/confirmResponse';
import {
  codeBlockPlainText,
  languageFromPreChildren,
  trimCodeFence,
} from '@/lib/markdownCode';
import { stampFromIso } from '@/lib/relativeStamp';
import { api } from '@/lib/api';
import { cleanSpeechText } from '@/lib/speechText';
import { canRetryLastTurn, chatTurnOptions, lastUserPrompt } from '@/lib/retryLastTurn';
import { toolDisplayName } from '@/lib/apiText';
import { getAudioQueue, getNativeSpeechQueue, type ChatBubble, useChatStore } from '@/stores/chatStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { quoteToComposer, useUIStore } from '@/stores/uiStore';
import { useI18n } from '@/lib/i18n';
import { BUBBLE_COLLAPSE_MAX_PX } from '@/lib/messageCollapse';
import { MessageCollapse } from './MessageCollapse';
import { SourceList } from './SourceList';
import { ToolCallCard } from './ToolCallCard';

interface Props {
  message: ChatBubble;
  streaming?: boolean;
}

function MessageBubbleImpl({ message, streaming }: Props): JSX.Element {
  const { t, language } = useI18n();
  const [copied, setCopied] = useState(false);
  const [showThinking, setShowThinking] = useState(false);
  const settings = useSettingsStore((state) => state.settings);
  const pushToast = useUIStore((state) => state.pushToast);
  const messages = useChatStore((state) => state.messages);
  const generating = useChatStore((state) => state.generating);
  const sendMessage = useChatStore((state) => state.sendMessage);
  const isUser = message.role === 'user';
  const showRetry =
    !streaming &&
    !isUser &&
    canRetryLastTurn({ generating, messages }) &&
    messages[messages.length - 1]?.id === message.id;

  const copyContent = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(
        hudMessagePlainText(message.content, message.toolCalls),
      );
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      pushToast('error', t('toast.copyFail'));
    }
  };

  const speak = async (): Promise<void> => {
    try {
      const speechText = cleanSpeechText(message.content).slice(0, 2000);
      if (!speechText) {
        pushToast('warning', t('toast.speakEmpty'));
        return;
      }
      if (settings.ttsVoice.startsWith('windows:')) {
        getNativeSpeechQueue().enqueue(
          speechText,
          settings.ttsVoice.replace(/^windows:/, ''),
          settings.ttsSpeed,
        );
        return;
      }
      const blob = await api.speech.synthesize(
        speechText,
        settings.ttsVoice,
        settings.ttsSpeed,
      );
      getAudioQueue().enqueueBlob(blob);
    } catch (error) {
      pushToast('error', error instanceof Error ? error.message : t('toast.speakFail'));
    }
  };

  return (
    <div className={cn('flex animate-fade-in gap-3', isUser && 'flex-row-reverse')}>
      {/* Avatar */}
      <div
        className={cn(
          'flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-xs font-semibold',
          isUser
            ? 'bg-slate-700 text-slate-200'
            : 'bg-gradient-to-br from-uryx-accent to-uryx-accent2 text-slate-950',
        )}
      >
        {isUser ? <User size={15} /> : 'J'}
      </div>

      <div
        className={cn('min-w-0 max-w-[min(760px,80%)] flex-1', isUser && 'flex flex-col items-end')}
      >
        {/* Araç çağrıları */}
        {!isUser && message.toolCalls && message.toolCalls.length > 0 && (
          <div className="mb-2 w-full space-y-1.5">
            {message.toolCalls.map((call, index) => (
              <ToolCallCard
                key={`${call.tool_name}-${index}`}
                toolName={call.tool_name}
                displayName={toolDisplayName(
                  call.tool_name,
                  call.display_name ?? call.tool_name,
                  language,
                )}
                args={call.arguments ?? {}}
                status={summarizedToolStatus(call.tool_name, call)}
                error={call.error ?? undefined}
                durationMs={call.duration_ms}
                result={call.result}
              />
            ))}
          </div>
        )}

        {/* Düşünme */}
        {!isUser && message.thinking && (
          <div className="mb-2 w-full">
            <button
              type="button"
              onClick={() => setShowThinking((value) => !value)}
              className="flex items-center gap-1.5 text-[11px] text-slate-500 transition-colors hover:text-slate-300"
            >
              <Brain size={12} />
              {showThinking ? t('msg.thinkingHide') : t('msg.thinkingShow')}
            </button>
            {showThinking && (
              <pre className="mt-1.5 max-h-64 overflow-y-auto whitespace-pre-wrap rounded-lg border border-uryx-border bg-black/30 p-3 font-mono text-[12px] leading-relaxed text-slate-400">
                {message.thinking}
              </pre>
            )}
          </div>
        )}

        {/* Gövde */}
        {(message.content || streaming) && (
          <div
            className={cn(
              'group relative rounded-xl px-4 py-3',
              isUser
                ? 'bg-uryx-accent/15 text-slate-100'
                : 'border border-uryx-border bg-uryx-surface',
            )}
          >
            <MessageCollapse
              contentKey={message.id + (message.content || '')}
              maxHeight={BUBBLE_COLLAPSE_MAX_PX}
              disabled={Boolean(streaming)}
              buttonClassName="mt-2 text-[11px] text-uryx-accent hover:underline"
            >
              {isUser ? (
                <p className="whitespace-pre-wrap break-words text-[14.5px] leading-relaxed">
                  {message.content}
                </p>
              ) : (
                <div className="markdown break-words">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    rehypePlugins={[rehypeHighlight]}
                    components={{ img: MarkdownImage, pre: MarkdownPre }}
                    urlTransform={safeMarkdownUrl}
                  >
                    {message.content}
                  </ReactMarkdown>
                  {streaming && (
                    <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-uryx-accent align-text-bottom" />
                  )}
                </div>
              )}
            </MessageCollapse>

            {/* Eylemler */}
            {!streaming && message.content && (
              <div
                className={cn(
                  'absolute -top-2.5 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100',
                  isUser ? 'left-2' : 'right-2',
                )}
              >
                <button
                  type="button"
                  onClick={() => void copyContent()}
                  className="rounded-md border border-uryx-border bg-uryx-panel p-1.5 text-slate-400 transition-colors hover:text-slate-100"
                  title={t('action.copy')}
                >
                  {copied ? <Check size={12} className="text-uryx-ok" /> : <Copy size={12} />}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    if (!quoteToComposer(quoteMessageText(message.content, message.toolCalls))) {
                      pushToast('warning', t('toast.quoteEmpty'));
                    }
                  }}
                  className="rounded-md border border-uryx-border bg-uryx-panel p-1.5 text-slate-400 transition-colors hover:text-slate-100"
                  title={t('hud.action.quote')}
                >
                  <Quote size={12} />
                </button>
                {!isUser && (
                  <button
                    type="button"
                    onClick={() => void speak()}
                    className="rounded-md border border-uryx-border bg-uryx-panel p-1.5 text-slate-400 transition-colors hover:text-slate-100"
                    title={t('action.speak')}
                  >
                    <Volume2 size={12} />
                  </button>
                )}
                {showRetry && (
                  <button
                    type="button"
                    onClick={() => {
                      const prompt = lastUserPrompt(messages);
                      if (!prompt || !sendMessage(prompt, chatTurnOptions(settings))) {
                        pushToast('warning', t('toast.retryEmpty'));
                        return;
                      }
                      pushToast('success', t('toast.retryOk'));
                    }}
                    className="rounded-md border border-uryx-border bg-uryx-panel p-1.5 text-slate-400 transition-colors hover:text-slate-100"
                    title={t('hud.action.retry')}
                    aria-label={t('hud.action.retryLast')}
                  >
                    <RefreshCw size={12} />
                  </button>
                )}
              </div>
            )}
          </div>
        )}

        {message.stopped && (
          <p className="mt-2 px-1 text-[11.5px] text-slate-500">{t('msg.stopped')}</p>
        )}

        {/* Hata */}
        {message.error && (
          <div className="mt-2 flex w-full items-start gap-2 rounded-lg border border-uryx-danger/40 bg-uryx-danger/10 px-3 py-2">
            <AlertCircle size={15} className="mt-0.5 shrink-0 text-uryx-danger" />
            <p className="text-[13px] leading-snug text-rose-200">{message.error}</p>
          </div>
        )}

        {/* Kaynaklar */}
        {!isUser && message.sources && message.sources.length > 0 && (
          <SourceList sources={message.sources} />
        )}

        {/* Zaman */}
        <p
          className={cn('mt-1 px-1 text-[10.5px] text-slate-600', isUser && 'text-right')}
          title={stampFromIso(message.createdAt, new Date(), language).title}
        >
          {stampFromIso(message.createdAt, new Date(), language).label}
        </p>
      </div>
    </div>
  );
}

export const MessageBubble = memo(MessageBubbleImpl);

export function safeMarkdownUrl(url: string): string {
  return /^(https:\/\/|mailto:|data:image\/|blob:|uryx-media:)/i.test(url) ? url : '';
}

/** BetterChatGPT CodeBar — çitli blokta dil + kopyala. */
export function MarkdownPre({ children }: { children?: ReactNode }): JSX.Element {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  const language = languageFromPreChildren(children);
  const text = trimCodeFence(codeBlockPlainText(children));

  const copyCode = async (): Promise<void> => {
    if (!text.trim()) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
    }
  };

  return (
    <div className="markdown-code">
      <div className="markdown-code__bar">
        <span>{language || 'code'}</span>
        <button type="button" onClick={() => void copyCode()} title={t('action.copyCode')}>
          {copied ? t('action.copied') : t('action.copy')}
        </button>
      </div>
      <pre>{children}</pre>
    </div>
  );
}

export function MarkdownImage({ src, alt }: { src?: string; alt?: string }): JSX.Element | null {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  if (!src || !/^(https:\/\/|data:image\/|blob:|uryx-media:)/i.test(src)) return null;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="hud-image-object group relative block w-full overflow-hidden border border-uryx-border bg-black/40"
        title={t('action.fullscreen')}
      >
        <span className="hud-image-object__header">{t('hud.image.preview')}</span>
        <img src={src} alt={alt ?? t('hud.image.alt')} className="max-h-80 w-full object-contain" />
        <span className="absolute right-2 top-2 rounded-md bg-black/70 p-1.5 text-white opacity-0 transition-opacity group-hover:opacity-100">
          <Maximize2 size={14} />
        </span>
      </button>
      {open &&
        createPortal(
          <div
            className="fixed inset-0 z-[100] flex items-center justify-center bg-black/90 p-6"
            role="dialog"
            aria-modal="true"
            onClick={() => setOpen(false)}
          >
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="absolute right-5 top-5 rounded-md border border-white/15 bg-black/70 p-2 text-white hover:bg-white/10"
              title={t('action.close')}
            >
              <X size={18} />
            </button>
            <img
              src={src}
              alt={alt ?? t('hud.image.altFull')}
              className="max-h-full max-w-full object-contain"
              onClick={(event) => event.stopPropagation()}
            />
          </div>,
          document.body,
        )}
    </>
  );
}
