/**
 * Mesaj yazma alanı: metin kutusu, mikrofon, push-to-talk ve tur seçenekleri.
 *
 * Mikrofon iki modda çalışır:
 *  - **Tıkla-konuş**: butona basılır, VAD sessizliği algılayınca otomatik durur.
 *  - **Push-to-talk**: basılı tutulduğu sürece kayıt alır (fare veya kısayol).
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Brain, Loader2, Mic, Send, Square, Volume2, VolumeX, Wrench, Zap } from 'lucide-react';

import { api, ApiError } from '@/lib/api';
import { MicRecorder, MicrophoneSession } from '@/lib/audio';
import { cn } from '@/lib/cn';
import { readComposerDraft, writeComposerDraft } from '@/lib/composerDraft';
import { enqueueComposer } from '@/lib/composerQueue';
import { mergeQuoteIntoDraft } from '@/lib/composerQuote';
import { applyComposerRecall, userPromptsNewestFirst } from '@/lib/composerRecall';
import { parseComposerInput } from '@/lib/composerSlash';
import { chatTurnOptions } from '@/lib/retryLastTurn';
import { formatSttHudCaption, SttStream } from '@/lib/sttStream';
import { useI18n } from '@/lib/i18n';
import { extractWakeCommand, classifyIdleWake } from '@/lib/wakeWord';
import { useChatStore } from '@/stores/chatStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { openHistorySearch, useUIStore } from '@/stores/uiStore';
import { VoiceIndicator } from './VoiceIndicator';

const WAKE_IDLE_LISTEN_MS = 15_000;

export function Composer({ variant = 'default' }: { variant?: 'default' | 'hud' }): JSX.Element {
  const [text, setText] = useState('');
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [level, setLevel] = useState(0);
  const [queue, setQueue] = useState<string[]>([]);
  const wasGeneratingRef = useRef(false);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const textRef = useRef('');
  const recorderRef = useRef<MicRecorder | null>(null);
  const sttStreamRef = useRef<SttStream | null>(null);
  const wakeRecorderRef = useRef<MicRecorder | null>(null);
  const [microphoneSession] = useState(() => new MicrophoneSession());
  const pushToTalkRef = useRef(false);
  const handledVoiceToggleRef = useRef(0);
  const manualRecordingStartingRef = useRef(false);
  const lastRecalledRef = useRef('');
  const skipDraftWriteRef = useRef(true);
  const wakeConversationRef = useRef(false);
  const awaitingWakeResponseRef = useRef(false);
  const wakeResponseWasBusyRef = useRef(false);
  const sendContentRef = useRef<(content: string) => boolean>(() => false);
  const startRecordingRef = useRef<() => Promise<void>>(async () => undefined);
  const wakeBusyRef = useRef({
    generating: false,
    speaking: false,
    recording: false,
    transcribing: false,
  });

  const { settings, update } = useSettingsStore();
  const { t } = useI18n();
  const sttLanguage = settings.language === 'en' ? 'en' : 'tr';
  const pushToast = useUIStore((state) => state.pushToast);
  const setView = useUIStore((state) => state.setView);
  const setVoiceState = useUIStore((state) => state.setVoiceState);
  const setVoiceLevel = useUIStore((state) => state.setVoiceLevel);
  const setSttPartial = useUIStore((state) => state.setSttPartial);
  const voiceToggleRequest = useUIStore((state) => state.voiceToggleRequest);
  const composerQuoteTick = useUIStore((state) => state.composerQuoteTick);
  const composerFocusTick = useUIStore((state) => state.composerFocusTick);
  const {
    generating,
    connection,
    sendMessage,
    cancel,
    newConversation,
    stopSpeech,
    speaking,
    pendingConfirmation,
    respondConfirmation,
    messages,
    conversationId,
  } = useChatStore();

  const connected = connection === 'open';

  wakeBusyRef.current = { generating, speaking, recording, transcribing };

  /** Metin kutusu yüksekliğini içeriğe göre ayarlar. */
  const autoResize = useCallback(() => {
    const element = textareaRef.current;
    if (!element) return;
    element.style.height = 'auto';
    element.style.height = `${Math.min(element.scrollHeight, 200)}px`;
  }, []);

  useEffect(autoResize, [text, autoResize]);

  useEffect(() => {
    skipDraftWriteRef.current = true;
    const saved = readComposerDraft(conversationId);
    setText(saved);
    textRef.current = saved;
    lastRecalledRef.current = '';
  }, [conversationId]);

  useEffect(() => {
    textRef.current = text;
    if (skipDraftWriteRef.current) {
      skipDraftWriteRef.current = false;
      return;
    }
    writeComposerDraft(text, conversationId);
  }, [text, conversationId]);

  useEffect(() => {
    if (!composerQuoteTick) return;
    const quote = useUIStore.getState().composerQuote;
    if (!quote) return;
    setText((current) => {
      const next = mergeQuoteIntoDraft(current, quote);
      textRef.current = next;
      return next;
    });
    lastRecalledRef.current = '';
    window.requestAnimationFrame(() => {
      const box = textareaRef.current;
      if (!box) return;
      box.focus();
      box.selectionStart = box.selectionEnd = box.value.length;
    });
  }, [composerQuoteTick]);

  useEffect(() => {
    if (!composerFocusTick) return;
    window.requestAnimationFrame(() => textareaRef.current?.focus());
  }, [composerFocusTick]);

  const sendContent = useCallback(
    (content: string): boolean => {
      const clean = content.trim();
      if (!clean) return false;
      const parsed = parseComposerInput(clean);
      if ('slash' in parsed) {
        if (parsed.slash === 'newChat') {
          newConversation();
          setView('chat');
          return true;
        }
        if (parsed.slash === 'stop') {
          cancel();
          return true;
        }
        if (parsed.slash === 'settings') {
          setView('settings');
          return true;
        }
        openHistorySearch();
        return true;
      }
      if (generating) {
        setQueue((current) => enqueueComposer(parsed.send, current));
        return true;
      }
      if (!connected) {
        pushToast('error', t('composer.offline'));
        return false;
      }

      const sent = sendMessage(parsed.send, chatTurnOptions(settings));
      if (sent) setView('chat');
      else pushToast('error', t('composer.sendFail'));
      return sent;
    },
    [cancel, connected, generating, newConversation, pushToast, sendMessage, settings, setView, t],
  );

  useEffect(() => {
    if (wasGeneratingRef.current && !generating && queue[0]) {
      const next = queue[0];
      if (sendContent(next)) setQueue((current) => current.slice(1));
    }
    wasGeneratingRef.current = generating;
  }, [generating, queue, sendContent]);

  /** Kaydı bitirir ve transkripsiyon yapar. */
  const finishRecording = useCallback(async () => {
    const recorder = recorderRef.current;
    if (!recorder) return;
    recorderRef.current = null;

    setRecording(false);
    setLevel(0);
    setVoiceLevel(0);
    setVoiceState('transcribing');
    const hadSpeech = recorder.hadSpeech;
    const blob = await recorder.stop();

    if (!blob || !hadSpeech) {
      sttStreamRef.current?.close();
      sttStreamRef.current = null;
      setSttPartial('');
      if (wakeConversationRef.current) {
        wakeConversationRef.current = false;
        awaitingWakeResponseRef.current = false;
        pushToast('info', t('composer.listenClosedWake'));
      } else {
        pushToast('warning', t('composer.recordShort'));
      }
      setVoiceState('idle');
      return;
    }

    setTranscribing(true);
    try {
      const streamed = (await sttStreamRef.current?.end(sttLanguage))?.trim() ?? '';
      sttStreamRef.current = null;
      const result = streamed
        ? { text: streamed }
        : await api.speech.transcribe(blob, sttLanguage, false);
      const transcript = result.text.trim();
      if (!transcript) {
        pushToast('warning', t('composer.noSpeech'));
        return;
      }
      if (wakeConversationRef.current && conversationStopIntent(transcript)) {
        wakeConversationRef.current = false;
        awaitingWakeResponseRef.current = false;
        pushToast('info', t('composer.listenClosed'));
        return;
      }
      const confirmation = confirmationIntent(transcript);
      if (pendingConfirmation && confirmation !== null) {
        respondConfirmation(confirmation);
        pushToast('info', confirmation ? t('composer.confirmOk') : t('composer.confirmCancel'));
        return;
      }
      const current = textRef.current.trim();
      const content = current ? `${current} ${transcript}` : transcript;
      if (settings.voiceAutoSend && sendContent(content)) {
        if (wakeConversationRef.current) {
          awaitingWakeResponseRef.current = true;
          wakeResponseWasBusyRef.current = false;
        }
        setText('');
        textRef.current = '';
        window.requestAnimationFrame(autoResize);
      } else {
        setText(content);
        textRef.current = content;
        textareaRef.current?.focus();
      }
    } catch (error) {
      const message =
        error instanceof ApiError
          ? error.message
          : t('composer.sttFail');
      pushToast('error', message);
    } finally {
      setTranscribing(false);
      setVoiceState('idle');
      setSttPartial('');
    }
  }, [
    autoResize,
    pendingConfirmation,
    pushToast,
    respondConfirmation,
    sendContent,
    setSttPartial,
    setVoiceLevel,
    setVoiceState,
    settings.voiceAutoSend,
    sttLanguage,
    t,
  ]);

  /** Kaydı başlatır. */
  const startRecording = useCallback(async () => {
    if (recorderRef.current || transcribing || manualRecordingStartingRef.current) return;

    manualRecordingStartingRef.current = true;
    wakeRecorderRef.current?.cancel();
    wakeRecorderRef.current = null;

    stopSpeech();
    const recorder = await microphoneSession.createRecorder({
      deviceId: settings.microphoneDeviceId,
      noiseThreshold: settings.micNoiseThreshold,
      adaptiveNoiseFloor: settings.adaptiveVadEnabled,
      silenceTimeoutMs:
        pushToTalkRef.current || !settings.vadEnabled ? 0 : settings.vadSilenceTimeoutMs,
      initialSilenceTimeoutMs: wakeConversationRef.current ? settings.followUpListenMs : 12_000,
      onLevel: (nextLevel) => {
        setLevel(nextLevel);
        setVoiceLevel(nextLevel);
      },
      onAutoStop: () => void finishRecording(),
      onChunk: (chunk) => {
        void sttStreamRef.current?.sendChunk(chunk);
      },
    });

    try {
      const stream = new SttStream();
      setSttPartial('');
      const opened = await stream.connect((partial) => {
        setSttPartial(formatSttHudCaption(partial));
      });
      sttStreamRef.current = opened ? stream : null;
      if (!opened) stream.close();
      await recorder.start();
      recorderRef.current = recorder;
      setRecording(true);
      setVoiceState('listening');
    } catch (error) {
      setVoiceState('idle');
      setSttPartial('');
      pushToast('error', error instanceof Error ? error.message : t('composer.micFail'));
    } finally {
      manualRecordingStartingRef.current = false;
    }
  }, [
    settings.microphoneDeviceId,
    settings.micNoiseThreshold,
    settings.adaptiveVadEnabled,
    settings.followUpListenMs,
    settings.vadEnabled,
    settings.vadSilenceTimeoutMs,
    transcribing,
    stopSpeech,
    finishRecording,
    microphoneSession,
    pushToast,
    setSttPartial,
    setVoiceLevel,
    setVoiceState,
    t,
  ]);

  sendContentRef.current = sendContent;
  startRecordingRef.current = startRecording;

  /** Mikrofon butonuna tıklama (tıkla-konuş). */
  const toggleRecording = (): void => {
    pushToTalkRef.current = false;
    if (recording) {
      void finishRecording();
    } else {
      void startRecording();
    }
  };

  useEffect(() => {
    if (voiceToggleRequest === 0 || handledVoiceToggleRef.current === voiceToggleRequest) {
      return;
    }
    handledVoiceToggleRef.current = voiceToggleRequest;
    pushToTalkRef.current = false;
    if (recorderRef.current) void finishRecording();
    else void startRecording();
  }, [voiceToggleRequest, finishRecording, startRecording]);

  useEffect(() => {
    if (!settings.wakeWordEnabled || !settings.wakeWord.trim() || !connected) {
      wakeRecorderRef.current?.cancel();
      wakeRecorderRef.current = null;
      return;
    }

    let cancelled = false;
    let microphoneErrorShown = false;

    const listen = async (): Promise<void> => {
      while (!cancelled) {
        const busy = wakeBusyRef.current;
        if (
          (busy.generating && !(busy.speaking && settings.bargeInEnabled)) ||
          (busy.speaking && !settings.bargeInEnabled) ||
          busy.recording ||
          busy.transcribing ||
          manualRecordingStartingRef.current ||
          recorderRef.current ||
          wakeConversationRef.current
        ) {
          await delay(450);
          continue;
        }

        const recorder = await microphoneSession.createRecorder({
          deviceId: settings.microphoneDeviceId,
          noiseThreshold: settings.micNoiseThreshold,
          adaptiveNoiseFloor: settings.adaptiveVadEnabled,
          silenceTimeoutMs: settings.vadSilenceTimeoutMs,
          initialSilenceTimeoutMs: WAKE_IDLE_LISTEN_MS,
          capturePcm: true,
        });
        wakeRecorderRef.current = recorder;

        try {
          const autoStop = recorder.waitForAutoStop();
          await recorder.start();
          await autoStop;
          if (cancelled || wakeRecorderRef.current !== recorder) {
            recorder.cancel();
            continue;
          }

          const hadSpeech = recorder.hadSpeech;
          const pcm = recorder.takePcm();
          const blob = await recorder.stop();
          wakeRecorderRef.current = null;
          if (!hadSpeech || cancelled) continue;

          let command: string | null = null;
          const decision = await classifyIdleWake({
            host: pcm?.samples.length ? window.uryx?.wake : undefined,
            samples: pcm?.samples ?? new Float32Array(0),
            sampleRate: pcm?.sampleRate ?? 16_000,
          });
          if (decision === 'onnx_miss') continue;
          if (decision === 'onnx_hit') {
            command = '';
          } else {
            if (!blob) continue;
            const result = await api.speech.transcribe(blob, sttLanguage, true);
            if (cancelled) continue;
            command = extractWakeCommand(result.text, settings.wakeWord);
          }
          if (command === null) continue;

          if (wakeBusyRef.current.speaking) {
            stopSpeech();
            cancel();
          }

          wakeConversationRef.current = true;
          await window.uryx?.window.show();
          useUIStore.getState().setView('chat');
          if (command) {
            pushToast('success', t('composer.wakeHeard', { command }));
            if (sendContentRef.current(command)) {
              awaitingWakeResponseRef.current = true;
              wakeResponseWasBusyRef.current = false;
            } else {
              wakeConversationRef.current = false;
            }
          } else {
            pushToast('success', t('composer.wakeListening'));
            await startRecordingRef.current();
          }
        } catch (error) {
          recorder.cancel();
          if (!cancelled && !microphoneErrorShown) {
            microphoneErrorShown = true;
            pushToast(
              'error',
              error instanceof Error ? error.message : t('composer.wakeMicFail'),
            );
          }
          await delay(3_000);
        } finally {
          if (wakeRecorderRef.current === recorder) wakeRecorderRef.current = null;
        }
      }
    };

    void listen();
    return () => {
      cancelled = true;
      wakeRecorderRef.current?.cancel();
      wakeRecorderRef.current = null;
    };
  }, [
    connected,
    cancel,
    microphoneSession,
    pushToast,
    settings.adaptiveVadEnabled,
    settings.bargeInEnabled,
    settings.micNoiseThreshold,
    settings.microphoneDeviceId,
    settings.vadSilenceTimeoutMs,
    settings.wakeWord,
    settings.wakeWordEnabled,
    sttLanguage,
    stopSpeech,
  ]);

  useEffect(() => {
    if (!settings.wakeWordEnabled) {
      wakeConversationRef.current = false;
      awaitingWakeResponseRef.current = false;
      return;
    }
    if (!awaitingWakeResponseRef.current) return;
    if (generating || speaking) {
      wakeResponseWasBusyRef.current = true;
      return;
    }
    if (
      !wakeResponseWasBusyRef.current ||
      recording ||
      transcribing ||
      recorderRef.current ||
      manualRecordingStartingRef.current
    ) {
      return;
    }

    awaitingWakeResponseRef.current = false;
    wakeResponseWasBusyRef.current = false;
    const timer = window.setTimeout(() => void startRecordingRef.current(), 600);
    return () => window.clearTimeout(timer);
  }, [generating, recording, settings.wakeWordEnabled, speaking, transcribing]);

  useEffect(() => {
    const bridge = window.uryx;
    if (!bridge) return;
    return bridge.on('shortcut:pushToTalk', () => {
      pushToTalkRef.current = true;
      if (recorderRef.current) {
        void finishRecording();
      } else {
        void startRecording();
      }
    });
  }, [startRecording, finishRecording]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.code === 'Space' && event.ctrlKey && !event.repeat && !recorderRef.current) {
        event.preventDefault();
        pushToTalkRef.current = true;
        void startRecording();
      }
    };
    const onKeyUp = (event: KeyboardEvent): void => {
      if (event.code === 'Space' && pushToTalkRef.current && recorderRef.current) {
        event.preventDefault();
        pushToTalkRef.current = false;
        void finishRecording();
      }
    };

    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('keyup', onKeyUp);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('keyup', onKeyUp);
    };
  }, [startRecording, finishRecording]);

  useEffect(
    () => () => {
      recorderRef.current?.cancel();
      wakeRecorderRef.current?.cancel();
      microphoneSession.close();
      setVoiceLevel(0);
      setVoiceState('idle');
    },
    [microphoneSession, setVoiceLevel, setVoiceState],
  );

  /** Mesajı gönderir. */
  const submit = (): void => {
    const content = text.trim();
    if (!content) return;
    const confirmation = confirmationIntent(content);
    if (pendingConfirmation && confirmation !== null) {
      respondConfirmation(confirmation);
      setText('');
      textRef.current = '';
      lastRecalledRef.current = '';
      return;
    }
    if (sendContent(content)) {
      setText('');
      textRef.current = '';
      lastRecalledRef.current = '';
      window.requestAnimationFrame(autoResize);
    }
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>): void => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submit();
      return;
    }
    if (
      (event.key === 'ArrowUp' || event.key === 'ArrowDown') &&
      !event.shiftKey &&
      !event.altKey &&
      !event.ctrlKey &&
      !event.metaKey
    ) {
      const next = applyComposerRecall(
        text,
        userPromptsNewestFirst(messages),
        event.key,
        lastRecalledRef.current,
      );
      if (!next) return;
      event.preventDefault();
      lastRecalledRef.current = next.recalled;
      setText(next.text);
      textRef.current = next.text;
    }
  };

  return (
    <div
      className={cn(
        variant === 'hud'
          ? 'uryx-terminal-composer'
          : 'shrink-0 border-t border-uryx-border bg-uryx-surface px-6 py-3',
      )}
    >
      {/* Seçenek çubuğu */}
      {variant === 'default' && (
        <div className="mb-2 flex flex-wrap items-center gap-1.5">
          <ToggleChip
            active={settings.toolsEnabled}
            icon={<Wrench size={12} />}
            label={t('view.tools')}
            onClick={() => void update({ toolsEnabled: !settings.toolsEnabled })}
          />
          <ToggleChip
            active={settings.ragEnabled}
            icon={<Zap size={12} />}
            label={t('composer.toggle.rag')}
            onClick={() => void update({ ragEnabled: !settings.ragEnabled })}
          />
          <ToggleChip
            active={settings.thinkingMode}
            icon={<Brain size={12} />}
            label={t('settings.thinking')}
            onClick={() => void update({ thinkingMode: !settings.thinkingMode })}
          />
          <ToggleChip
            active={settings.conciseMode}
            icon={<Zap size={12} />}
            label={t('settings.concise')}
            onClick={() => void update({ conciseMode: !settings.conciseMode })}
          />
          <ToggleChip
            active={settings.ttsEnabled}
            icon={settings.ttsEnabled ? <Volume2 size={12} /> : <VolumeX size={12} />}
            label={t('settings.ttsEnable')}
            onClick={() => {
              if (settings.ttsEnabled) stopSpeech();
              void update({ ttsEnabled: !settings.ttsEnabled });
            }}
          />

          {speaking && (
            <button
              type="button"
              onClick={stopSpeech}
              className="badge ml-auto bg-uryx-accent/15 text-uryx-accent transition-colors hover:bg-uryx-accent/25"
            >
              <Square size={10} />
              {t('composer.stopSpeech')}
            </button>
          )}
        </div>
      )}

      {/* Giriş */}
      <div
        className={cn(
          'flex items-end gap-2 border bg-uryx-bg p-2 transition-colors',
          variant === 'default' && 'rounded-xl',
          recording
            ? 'border-uryx-danger/60'
            : 'border-uryx-border focus-within:border-uryx-accent/60',
        )}
      >
        {/* Mikrofon */}
        <button
          type="button"
          onClick={toggleRecording}
          onMouseDown={(event) => {
            if (event.button === 2) {
              pushToTalkRef.current = true;
              void startRecording();
            }
          }}
          onMouseUp={() => {
            if (pushToTalkRef.current) {
              pushToTalkRef.current = false;
              void finishRecording();
            }
          }}
          onContextMenu={(event) => event.preventDefault()}
          disabled={transcribing}
          className={cn(
            'flex h-10 w-10 shrink-0 items-center justify-center transition-colors',
            variant === 'default' && 'rounded-lg',
            recording
              ? 'bg-uryx-danger text-white'
              : 'text-slate-400 hover:bg-white/5 hover:text-slate-100',
            transcribing && 'cursor-wait opacity-60',
          )}
          title={recording ? t('composer.micStop') : t('composer.micStart')}
          aria-label={t('composer.mic')}
        >
          {transcribing ? <Loader2 size={17} className="animate-spin" /> : <Mic size={17} />}
        </button>

        {/* Metin */}
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
          placeholder={
            recording
              ? t('composer.listening')
              : transcribing
                ? t('composer.transcribing')
                : generating
                  ? t('composer.queued')
                  : t('composer.placeholder')
          }
          disabled={recording || transcribing}
          className={cn(
            'max-h-[200px] flex-1 resize-none bg-transparent py-2 leading-relaxed focus:outline-none disabled:cursor-not-allowed',
            variant === 'hud'
              ? 'font-mono text-[12px] text-[var(--hud-text)] placeholder:text-[var(--hud-muted)]'
              : 'text-[14.5px] text-slate-100 placeholder:text-slate-600',
          )}
        />

        {/* Gönder / Durdur */}
        {generating ? (
          <button
            type="button"
            onClick={cancel}
            className={cn(
              'flex h-10 w-10 shrink-0 items-center justify-center bg-uryx-danger/20 text-uryx-danger transition-colors hover:bg-uryx-danger/30',
              variant === 'default' && 'rounded-lg',
            )}
            title={t('composer.stopGen')}
            aria-label={t('composer.stopGen')}
          >
            <Square size={15} />
          </button>
        ) : (
          <button
            type="button"
            onClick={submit}
            disabled={!text.trim() || recording || transcribing}
            className={cn(
              'flex h-10 w-10 shrink-0 items-center justify-center transition-colors disabled:cursor-not-allowed',
              variant === 'hud'
                ? 'border border-[var(--hud-orange)] bg-[var(--hud-input)] text-[var(--hud-orange)] hover:bg-[var(--hud-orange)] hover:text-[var(--hud-on-primary)] disabled:border-[var(--hud-line)] disabled:bg-transparent disabled:text-[var(--hud-muted)]'
                : 'rounded-lg bg-uryx-accent text-slate-950 hover:brightness-110 disabled:bg-slate-700 disabled:text-slate-500',
            )}
            title={t('composer.send')}
            aria-label={t('composer.send')}
          >
            <Send size={16} />
          </button>
        )}
      </div>

      {/* Ses göstergesi / bağlantı uyarısı */}
      {queue.length > 0 && (
        <p className="mt-1.5 text-center text-[11.5px] text-slate-500">
          {t('composer.queuedCount', { n: queue.length })}
        </p>
      )}
      {recording ? (
        <VoiceIndicator level={level} />
      ) : !connected ? (
        <p className="mt-1.5 text-center text-[11.5px] text-uryx-warn">
            {t('composer.offlineBanner')}
        </p>
      ) : null}
    </div>
  );
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function confirmationIntent(text: string): boolean | null {
  const clean = text
    .toLocaleLowerCase('tr-TR')
    .replace(/[.!?,]/g, '')
    .trim();
  if (/^(devam et|onayla|onaylıyorum|yap|tamam|evet)$/.test(clean)) return true;
  if (/^(iptal|iptal et|hayır|vazgeç|reddet)$/.test(clean)) return false;
  return null;
}

function conversationStopIntent(text: string): boolean {
  const clean = text
    .toLocaleLowerCase('tr-TR')
    .replace(/[.!?,]/g, '')
    .trim();
  return /^(dinlemeyi bırak|dinlemeyi kapat|uyku modu|bu kadar|görüşürüz|teşekkürler uryx)$/.test(
    clean,
  );
}

/** Seçenek çubuğundaki aç/kapa etiketi. */
function ToggleChip({
  active,
  icon,
  label,
  onClick,
}: {
  active: boolean;
  icon: JSX.Element;
  label: string;
  onClick: () => void;
}): JSX.Element {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        'badge border transition-colors',
        active
          ? 'border-uryx-accent/40 bg-uryx-accent/15 text-uryx-accent'
          : 'border-uryx-border bg-transparent text-slate-500 hover:text-slate-300',
      )}
    >
      {icon}
      {label}
    </button>
  );
}
