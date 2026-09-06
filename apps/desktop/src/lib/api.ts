/**
 * Backend REST istemcisi.
 *
 * Tüm isteklere `X-Uryx-Token` eklenir (ayarlarda tanımlıysa). Hatalar
 * `ApiError` olarak normalize edilir; böylece arayüz her yerde aynı biçimde
 * anlaşılır Türkçe mesaj gösterebilir.
 */

import type {
  ConversationDetail,
  ConversationSummary,
  DocumentRecord,
  DocumentSearchHit,
  DocumentStats,
  MemoryRecord,
  MemoryRef,
  MemoryStats,
  ChatMessage as ApiChatMessage,
  STTStatus,
  SystemStatus,
  ToolListResponse,
  ToolResult,
  TranscriptionResult,
  VoiceListResponse,
  LlmCredentialsReveal,
  LlmCredentialsStatus,
  LlmCredentialsUpdate,
} from '@shared/api';

import { tNow } from '@/lib/tNow';
import { getUiLanguage } from '@/lib/uiLocale';

/** Normalize edilmiş API hatası. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string = 'unknown',
    readonly details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = 'ApiError';
  }

  /** Bağlantı kurulamadı mı (backend kapalı)? */
  get isNetworkError(): boolean {
    return this.status === 0;
  }
}

let baseUrl = 'http://127.0.0.1:8080';
let authToken = '';

/** İstemci yapılandırmasını günceller. */
export function configureApi(url: string, token: string): void {
  baseUrl = url.replace(/\/+$/, '');
  authToken = token;
}

/** Aktif backend adresi. */
export function getBaseUrl(): string {
  return baseUrl;
}

/** Aktif token. */
export function getToken(): string {
  return authToken;
}

function headers(extra: Record<string, string> = {}): Record<string, string> {
  const result: Record<string, string> = { ...extra };
  if (authToken) result['X-Uryx-Token'] = authToken;
  result['X-Uryx-Language'] = getUiLanguage();
  return result;
}

/** Hatalı cevabı `ApiError`'a çevirir. */
async function toApiError(response: Response): Promise<ApiError> {
  let code = `http_${response.status}`;
  let message = tNow('api.httpFail', { status: response.status });
  let details: Record<string, unknown> = {};

  try {
    const body = (await response.json()) as {
      error?: { code: string; message: string; details?: Record<string, unknown> };
    };
    if (body?.error) {
      code = body.error.code ?? code;
      message = body.error.message ?? message;
      details = body.error.details ?? {};
    }
  } catch {
  }

  if (response.status === 401) message = tNow('api.tokenInvalid');
  if (response.status === 503 && code === 'unknown') message = tNow('api.unavailable');

  return new ApiError(message, response.status, code, details);
}

/** Ortak fetch sarmalayıcısı. */
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, {
      ...init,
      headers: headers(init.headers as Record<string, string>),
    });
  } catch (error) {
    throw new ApiError(
      tNow('api.network'),
      0,
      'network_error',
      { cause: String(error) },
    );
  }

  if (!response.ok) throw await toApiError(response);
  if (response.status === 204) return undefined as T;

  const contentType = response.headers.get('content-type') ?? '';
  if (contentType.includes('application/json')) return (await response.json()) as T;
  return (await response.text()) as unknown as T;
}

/** JSON gövdeli istek. */
function jsonRequest<T>(path: string, method: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

const V1 = '/api/v1';

export const api = {
  /** Backend sağlık kontrolü (token gerektirmez). */
  async health(): Promise<{ status: string; version: string; services: Record<string, string> }> {
    return request('/health');
  },

  conversations: {
    list: (search?: string) =>
      request<ConversationSummary[]>(
        `${V1}/chat/conversations${search ? `?search=${encodeURIComponent(search)}` : ''}`,
      ),
    get: (id: string) => request<ConversationDetail>(`${V1}/chat/conversations/${id}`),
    messages: (id: string) => request<ApiChatMessage[]>(`${V1}/chat/conversations/${id}/messages`),
    create: (title = tNow('tray.newChat')) =>
      jsonRequest<ConversationSummary>(`${V1}/chat/conversations`, 'POST', { title }),
    rename: (id: string, title: string) =>
      jsonRequest<{ ok: boolean }>(`${V1}/chat/conversations/${id}`, 'PATCH', { title }),
    remove: (id: string) =>
      request<{ ok: boolean }>(`${V1}/chat/conversations/${id}`, { method: 'DELETE' }),
  },

  memory: {
    list: (params: { q?: string; category?: string } = {}) => {
      const search = new URLSearchParams();
      if (params.q) search.set('q', params.q);
      if (params.category) search.set('category', params.category);
      const query = search.toString();
      return request<MemoryRecord[]>(`${V1}/memory${query ? `?${query}` : ''}`);
    },
    stats: () => request<MemoryStats>(`${V1}/memory/stats`),
    create: (payload: {
      content: string;
      category?: string;
      importance?: number;
      pinned?: boolean;
      tags?: string[];
    }) => jsonRequest<MemoryRecord>(`${V1}/memory`, 'POST', payload),
    update: (
      id: string,
      payload: Partial<{ content: string; category: string; importance: number; pinned: boolean }>,
    ) => jsonRequest<MemoryRecord>(`${V1}/memory/${id}`, 'PATCH', payload),
    pin: (id: string, pinned: boolean) =>
      jsonRequest<{ ok: boolean }>(`${V1}/memory/${id}/pin?pinned=${pinned}`, 'POST'),
    remove: (id: string) => request<{ ok: boolean }>(`${V1}/memory/${id}`, { method: 'DELETE' }),
    search: (query: string, topK = 5) =>
      jsonRequest<MemoryRef[]>(`${V1}/memory/search`, 'POST', { query, top_k: topK }),
    reindex: () => jsonRequest<{ ok: boolean; message: string }>(`${V1}/memory/reindex`, 'POST'),
  },

  documents: {
    list: () => request<DocumentRecord[]>(`${V1}/documents`),
    stats: () => request<DocumentStats>(`${V1}/documents/stats`),
    supported: () => request<{ extensions: string[] }>(`${V1}/documents/supported`),
    upload: async (files: File[]) => {
      const form = new FormData();
      files.forEach((file) => form.append('files', file, file.name));
      return request<{ accepted: unknown[]; duplicates: unknown[]; failed: unknown[] }>(
        `${V1}/documents/upload`,
        { method: 'POST', body: form },
      );
    },
    ingestPath: (path: string, recursive = true) =>
      jsonRequest<{ accepted_count: number; skipped: unknown[] }>(
        `${V1}/documents/ingest-path`,
        'POST',
        { path, recursive, collection: 'documents' },
      ),
    search: (query: string, topK = 5) =>
      jsonRequest<DocumentSearchHit[]>(`${V1}/documents/search`, 'POST', {
        query,
        top_k: topK,
        collection: 'documents',
      }),
    reindex: (id: string) => jsonRequest<{ ok: boolean }>(`${V1}/documents/${id}/reindex`, 'POST'),
    remove: (id: string) => request<{ ok: boolean }>(`${V1}/documents/${id}`, { method: 'DELETE' }),
  },

  tools: {
    list: () => request<ToolListResponse>(`${V1}/tools`),
    execute: (toolName: string, args: Record<string, unknown>, confirmed = false) =>
      jsonRequest<ToolResult>(`${V1}/tools/execute`, 'POST', {
        tool_name: toolName,
        arguments: args,
        confirmed,
      }),
    setEnabled: (toolName: string, enabled: boolean) =>
      jsonRequest<{ ok: boolean }>(`${V1}/tools/${toolName}/enabled?enabled=${enabled}`, 'POST'),
    history: () => request<Record<string, unknown>[]>(`${V1}/tools/history`),
  },

  system: {
    status: () => request<SystemStatus>(`${V1}/system/status`),
    config: () => request<Record<string, unknown>>(`${V1}/system/config`),
    llmCredentials: () => request<LlmCredentialsStatus>(`${V1}/system/llm-credentials`),
    putLlmCredentials: (body: LlmCredentialsUpdate) =>
      jsonRequest<LlmCredentialsStatus>(`${V1}/system/llm-credentials`, 'PUT', body),
    revealLlmCredentials: () =>
      request<LlmCredentialsReveal>(`${V1}/system/llm-credentials/reveal`),
    deleteLlmCredentials: () =>
      request<LlmCredentialsStatus>(`${V1}/system/llm-credentials`, { method: 'DELETE' }),
    reportError: (message: string) =>
      jsonRequest<{ ok: boolean }>(`${V1}/system/error`, 'POST', { message }),
  },

    speech: {
    sttStatus: () => request<STTStatus>(`${V1}/speech/stt/status`),
    reloadStt: (model: string) =>
      jsonRequest<STTStatus>(`${V1}/speech/stt/reload`, 'POST', { model }),
    transcribe: async (blob: Blob, language = 'tr', vadFilter = false) => {
      const form = new FormData();
      const extension = blob.type.includes('webm') ? 'webm' : 'wav';
      form.append('file', blob, `kayit.${extension}`);
      form.append('language', language);
      form.append('vad_filter', String(vadFilter));
      return request<TranscriptionResult>(`${V1}/speech/stt/transcribe`, {
        method: 'POST',
        body: form,
      });
    },
    voices: () => request<VoiceListResponse>(`${V1}/speech/tts/voices`),
    ttsStatus: () => request<Record<string, unknown>>(`${V1}/speech/tts/status`),
    synthesizeUrl: () => `${baseUrl}${V1}/speech/tts/synthesize`,
    synthesize: async (text: string, voice?: string, speed?: number): Promise<Blob> => {
      const response = await fetch(`${baseUrl}${V1}/speech/tts/synthesize`, {
        method: 'POST',
        headers: headers({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ text, voice, speed }),
      });
      if (!response.ok) throw await toApiError(response);
      return response.blob();
    },
  },
};
