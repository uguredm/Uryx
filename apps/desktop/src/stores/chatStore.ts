/**
 * Sohbet durumu.
 *
 * WebSocket olaylarını tüketip mesaj listesini, akan cevabı, araç çağrılarını,
 * RAG kaynaklarını ve TTS kuyruğunu yönetir.
 */

import { create } from 'zustand';
import type { MemoryRef, SourceRef, ToolCallSummary } from '@shared/api';
import type { WSServerEvent, WSToolConfirmRequest } from '@shared/ws';

import { AudioQueue, NativeSpeechQueue } from '@/lib/audio';
import { ChatSocket, type ConnectionStatus } from '@/lib/chatSocket';
import {
  buildToolConfirmResponse,
  chatSocketLost,
  chatTurnIsActive,
  confirmMatchesCall,
  pendingConfirmToReplace,
  toolResultIsRejected,
} from '@/lib/confirmResponse';
import { trimLiveAssistant } from '@/lib/bargeIn';
import { api } from '@/lib/api';
import { memoryCategoryLabel, truncate } from '@/lib/format';
import { tNow } from '@/lib/tNow';
import { getUiLanguage } from '@/lib/uiLocale';
import { useUIStore } from '@/stores/uiStore';

export interface ChatBubble {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  thinking?: string;
  createdAt: string;
  streaming?: boolean;
  stopped?: boolean;
  error?: string;
  sources?: SourceRef[];
  memories?: MemoryRef[];
  toolCalls?: ToolCallSummary[];
}

export interface LiveToolCall {
  callId: string;
  toolName: string;
  displayName: string;
  arguments: Record<string, unknown>;
  status: 'running' | 'success' | 'failed' | 'rejected';
  result?: Record<string, unknown>;
  error?: string | null;
  durationMs?: number;
}

interface ChatState {
  connection: ConnectionStatus;
  connectionDetail: string | null;
  streamDropped: boolean;

  conversationId: string | null;
  messages: ChatBubble[];
  generating: boolean;
  streamContent: string;
  streamThinking: string;

  activeSources: SourceRef[];
  activeMemories: MemoryRef[];
  liveToolCalls: LiveToolCall[];

  speaking: boolean;
  ttsError: string | null;

  pendingConfirmation: WSToolConfirmRequest | null;
  sessionAllowedTools: string[];

  connect: (baseUrl: string, token: string) => void;
  reconnect: () => void;
  disconnect: () => void;
  sendMessage: (content: string, options: Record<string, unknown>) => boolean;
  cancel: () => void;
  respondConfirmation: (approved: boolean, allowMediumSession?: boolean) => void;
  newConversation: () => void;
  loadConversation: (conversationId: string) => Promise<void>;
  setVolume: (volume: number) => void;
  stopSpeech: () => void;
}

const audioQueue = new AudioQueue();
const nativeSpeechQueue = new NativeSpeechQueue();
let socket: ChatSocket | null = null;
let tokenBuffer = '';
let thinkingBuffer = '';
let streamFlush = 0;

function nowIso(): string {
  return new Date().toISOString();
}

function summarizeLiveToolCalls(calls: LiveToolCall[]): ToolCallSummary[] | undefined {
  if (!calls.length) return undefined;
  return calls.map((call) => ({
    tool_name: call.toolName,
    display_name: call.displayName,
    arguments: call.arguments,
    success: call.status === 'success',
    error: call.error ?? null,
    duration_ms: call.durationMs,
    rejected: call.status === 'rejected',
    result: call.result,
  }));
}

function flushStreamBuffers(): void {
  streamFlush = 0;
  const tokens = tokenBuffer;
  const thinking = thinkingBuffer;
  tokenBuffer = '';
  thinkingBuffer = '';
  if (!tokens && !thinking) return;
  useChatStore.setState((state) => ({
    streamContent: tokens ? state.streamContent + tokens : state.streamContent,
    streamThinking: thinking ? state.streamThinking + thinking : state.streamThinking,
  }));
}

function queueStreamFlush(): void {
  if (streamFlush !== 0) return;
  streamFlush = window.requestAnimationFrame(flushStreamBuffers);
}

function resetStreamBuffers(): void {
  tokenBuffer = '';
  thinkingBuffer = '';
  if (streamFlush !== 0) {
    window.cancelAnimationFrame(streamFlush);
    streamFlush = 0;
  }
}

export const useChatStore = create<ChatState>((set, get) => {
  /** Sunucu olaylarını duruma uygular. */
  function applyEvent(event: WSServerEvent): void {
    switch (event.type) {
      case 'start': {
        resetStreamBuffers();
        set({
          conversationId: event.conversation_id,
          generating: true,
          streamContent: '',
          streamThinking: '',
          activeSources: [],
          activeMemories: [],
          liveToolCalls: [],
          pendingConfirmation: null,
        });
        break;
      }

      case 'token': {
        tokenBuffer += event.content;
        queueStreamFlush();
        break;
      }

      case 'thinking': {
        thinkingBuffer += event.content;
        queueStreamFlush();
        break;
      }

      case 'sources': {
        set({ activeSources: event.sources });
        break;
      }

      case 'memory_used': {
        set({ activeMemories: event.memories });
        break;
      }

      case 'memory_created': {
        const category = memoryCategoryLabel(event.category, getUiLanguage());
        const snippet = truncate(event.content, 90);
        useUIStore
          .getState()
          .pushToast('success', tNow('toast.memorySaved', { category, snippet }));
        break;
      }

      case 'tool_call': {
        set((state) => ({
          liveToolCalls: [
            ...state.liveToolCalls,
            {
              callId: event.call_id,
              toolName: event.tool_name,
              displayName: event.display_name,
              arguments: event.arguments,
              status: 'running',
            },
          ],
        }));
        break;
      }

      case 'tool_result': {
        set((state) => ({
          liveToolCalls: state.liveToolCalls.map((call) =>
            call.callId === event.call_id
              ? {
                  ...call,
                  status: event.success
                    ? 'success'
                    : toolResultIsRejected(event.error)
                      ? 'rejected'
                      : 'failed',
                  result: event.result,
                  error: event.error,
                  durationMs: event.duration_ms,
                }
              : call,
          ),
          pendingConfirmation: confirmMatchesCall(
            state.pendingConfirmation?.request_id,
            event.call_id,
          )
            ? null
            : state.pendingConfirmation,
        }));
        break;
      }

      case 'tool_confirm_request': {
        if (
          event.risk_level === 'medium' &&
          get().sessionAllowedTools.includes(event.tool_name)
        ) {
          socket?.send(buildToolConfirmResponse(event, true, true));
          break;
        }
        const replaced = pendingConfirmToReplace(get().pendingConfirmation, event);
        if (replaced) socket?.send(buildToolConfirmResponse(replaced, false));
        set({ pendingConfirmation: event });
        break;
      }

      case 'tts_chunk': {
        if (event.mime_type === 'application/x-uryx-windows-tts' && event.text) {
          nativeSpeechQueue.enqueue(
            event.text,
            event.voice ?? 'Microsoft Tolga',
            event.speed ?? 1,
            true,
          );
        } else if (event.audio_base64) {
          audioQueue.enqueueBase64(event.audio_base64, event.mime_type, event.text, true);
        }
        break;
      }

      case 'tts_status': {
        if (event.state === 'error') set({ ttsError: event.detail ?? tNow('toast.ttsError') });
        if (event.state === 'started') set({ ttsError: null });
        break;
      }

      case 'done': {
        flushStreamBuffers();
        const state = get();
        const bubble: ChatBubble = {
          id: event.message_id,
          role: 'assistant',
          content: event.content || state.streamContent,
          thinking: state.streamThinking || undefined,
          createdAt: nowIso(),
          sources: state.activeSources.length ? state.activeSources : undefined,
          memories: state.activeMemories.length ? state.activeMemories : undefined,
          toolCalls: summarizeLiveToolCalls(state.liveToolCalls),
        };
        set({
          messages: [...state.messages, bubble],
          generating: false,
          streamDropped: false,
          streamContent: '',
          streamThinking: '',
          conversationId: event.conversation_id,
          pendingConfirmation: null,
          liveToolCalls: [],
        });
        break;
      }

      case 'error': {
        flushStreamBuffers();
        const state = get();
        const partial = state.streamContent.trim();
        const bubble: ChatBubble = {
          id: `error-${Date.now()}`,
          role: 'assistant',
          content: partial,
          createdAt: nowIso(),
          error: event.message,
          toolCalls: summarizeLiveToolCalls(state.liveToolCalls),
        };
        set({
          messages: [...state.messages, bubble],
          generating: false,
          streamContent: '',
          streamThinking: '',
          pendingConfirmation: null,
          liveToolCalls: [],
        });
        break;
      }

      default:
        break;
    }
  }

  const syncSpeaking = (): void =>
    set({ speaking: audioQueue.isPlaying || nativeSpeechQueue.isPlaying });
  audioQueue.onStateChange = syncSpeaking;
  nativeSpeechQueue.onStateChange = syncSpeaking;

  return {
    connection: 'closed',
    connectionDetail: null,
    streamDropped: false,
    conversationId: null,
    messages: [],
    generating: false,
    streamContent: '',
    streamThinking: '',
    activeSources: [],
    activeMemories: [],
    liveToolCalls: [],
    speaking: false,
    ttsError: null,
    pendingConfirmation: null,
    sessionAllowedTools: [],

    connect: (baseUrl, token) => {
      socket ??= new ChatSocket({
        onEvent: applyEvent,
        onStatus: (status, detail) => {
          const state = get();
          const lost = chatSocketLost(status);
          const wasActive = chatTurnIsActive(state.generating, state.pendingConfirmation);
          if (lost && wasActive) {
            get().cancel();
          }
          set({
            connection: status,
            connectionDetail: detail ?? null,
            streamDropped: lost && wasActive ? true : status === 'open' ? false : get().streamDropped,
          });
        },
      });
      socket.connect(baseUrl, token);
    },

    reconnect: () => {
      get().cancel();
      socket?.reconnect();
    },

    disconnect: () => {
      get().cancel();
      socket?.close();
      socket = null;
      set({ connection: 'closed', pendingConfirmation: null, generating: false });
    },

    sendMessage: (content, options) => {
      const trimmed = content.trim();
      if (!trimmed || get().generating) return false;
      if (!socket?.isOpen) return false;

      const sent = socket.send({
        type: 'user_message',
        conversation_id: get().conversationId,
        content: trimmed,
        options: options as never,
      });
      if (!sent) return false;

      resetStreamBuffers();
      set((state) => ({
        messages: [
          ...state.messages,
          { id: `user-${Date.now()}`, role: 'user', content: trimmed, createdAt: nowIso() },
        ],
        generating: true,
        streamContent: '',
        streamThinking: '',
        activeSources: [],
        activeMemories: [],
        liveToolCalls: [],
        ttsError: null,
      }));
      return true;
    },

    cancel: () => {
      const state = get();
      if (chatTurnIsActive(state.generating, state.pendingConfirmation)) {
        socket?.send({ type: 'cancel' });
      }
      const spoken = [audioQueue.stop(), nativeSpeechQueue.stop()].filter(Boolean).join(' ').trim();
      if (!chatTurnIsActive(state.generating, state.pendingConfirmation) && !spoken) return;
      flushStreamBuffers();
      const flushed = get();
      const trimmed = trimLiveAssistant({
        streamContent: flushed.streamContent,
        messages: flushed.messages,
        spoken,
      });
      const partial = trimmed.streamContent.trim();
      const toolCalls = summarizeLiveToolCalls(flushed.liveToolCalls);
      const last = trimmed.messages.at(-1);
      const alreadyStopped = last?.role === 'assistant' && last.stopped;
      const bubble: ChatBubble | null =
        alreadyStopped || (!partial && !toolCalls)
          ? null
          : {
              id: `stopped-${Date.now()}`,
              role: 'assistant',
              content: partial,
              thinking: flushed.streamThinking || undefined,
              createdAt: nowIso(),
              stopped: true,
              toolCalls,
            };
      set({
        generating: false,
        streamContent: '',
        streamThinking: '',
        pendingConfirmation: null,
        liveToolCalls: [],
        messages: bubble ? [...trimmed.messages, bubble] : trimmed.messages,
      });
    },

    respondConfirmation: (approved, allowMediumSession = false) => {
      const pending = get().pendingConfirmation;
      if (!pending) return;
      socket?.send(buildToolConfirmResponse(pending, approved, allowMediumSession));
      const sessionAllowedTools =
        approved && allowMediumSession && pending.risk_level === 'medium'
          ? Array.from(new Set([...get().sessionAllowedTools, pending.tool_name]))
          : get().sessionAllowedTools;
      set({ pendingConfirmation: null, sessionAllowedTools });
    },

    newConversation: () => {
      get().cancel();
      set({
        conversationId: null,
        messages: [],
        streamContent: '',
        streamThinking: '',
        activeSources: [],
        activeMemories: [],
        liveToolCalls: [],
        generating: false,
        pendingConfirmation: null,
        sessionAllowedTools: [],
      });
    },

    loadConversation: async (conversationId) => {
      get().cancel();
      const detail = await api.conversations.get(conversationId);
      set({
        conversationId,
        messages: detail.messages
          .filter((m) => m.role === 'user' || m.role === 'assistant')
          .map((m) => ({
            id: m.id,
            role: m.role as 'user' | 'assistant',
            content: m.content,
            thinking: m.thinking ?? undefined,
            createdAt: m.created_at,
            sources: m.meta?.sources,
            memories: m.meta?.memories,
            toolCalls: m.meta?.tool_calls,
          })),
        streamContent: '',
        streamThinking: '',
        activeSources: [],
        activeMemories: [],
        liveToolCalls: [],
        generating: false,
        pendingConfirmation: null,
      });
    },

    setVolume: (volume) => {
      audioQueue.setVolume(volume);
      nativeSpeechQueue.setVolume(volume);
    },
    stopSpeech: () => {
      const spoken = [audioQueue.stop(), nativeSpeechQueue.stop()].filter(Boolean).join(' ').trim();
      if (!spoken) return;
      const state = get();
      const trimmed = trimLiveAssistant({
        streamContent: state.streamContent,
        messages: state.messages,
        spoken,
      });
      set({
        streamContent: trimmed.streamContent,
        messages: trimmed.messages,
      });
    },
  };
});

/** TTS kuyruğuna doğrudan erişim (ör. "tekrar seslendir" düğmesi). */
export function getAudioQueue(): AudioQueue {
  return audioQueue;
}

export function getNativeSpeechQueue(): NativeSpeechQueue {
  return nativeSpeechQueue;
}
