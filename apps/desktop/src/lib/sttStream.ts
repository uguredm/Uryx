/**
 * R&D 3 Whisper `/ws/transcribe` protokolü — masaüstü HTTP klip yerine parça.
 * API `/ws/speech/transcribe` yoksa sessizce düşer; Composer HTTP'ye döner.
 */

import { getBaseUrl, getToken } from '@/lib/api';

/** faster-whisper hotwords — prefix yok; her pencerede. */
export const STT_HOTWORDS = 'Uryx Whisper Piper Qdrant Docker';

export function sttStreamControl(
  kind: 'start' | 'end' | 'flush',
  language = 'tr',
): string {
  return JSON.stringify({ type: kind, language, hotwords: STT_HOTWORDS });
}

export function speechTranscribeWsUrl(baseUrl = getBaseUrl(), token = getToken()): string {
  const wsBase = baseUrl.replace(/^http/, 'ws').replace(/\/+$/, '');
  const params = token ? `?token=${encodeURIComponent(token)}` : '';
  return `${wsBase}/ws/speech/transcribe${params}`;
}

export function parseSttStreamEvent(raw: unknown): { kind: string; text: string } {
  if (!raw || typeof raw !== 'object') return { kind: '', text: '' };
  const event = raw as { type?: unknown; text?: unknown };
  return {
    kind: String(event.type ?? ''),
    text: String(event.text ?? '').trim(),
  };
}

/** whisper_streaming_web aperçu — HUD'da gri kesit; taslağı ezme. */
export function formatSttHudCaption(text: string, max = 96): string {
  const clean = text.replace(/\s+/g, ' ').trim();
  if (!clean) return '';
  return clean.length <= max ? clean : `${clean.slice(0, Math.max(1, max - 1))}…`;
}

export type SttSocketFactory = (url: string) => WebSocket;

export class SttStream {
  private socket: WebSocket | null = null;
  private last = '';

  constructor(private readonly createSocket: SttSocketFactory = (url) => new WebSocket(url)) {}

  async connect(onPartial?: (text: string) => void): Promise<boolean> {
    this.close();
    this.last = '';
    return new Promise((resolve) => {
      let settled = false;
      const finish = (ok: boolean): void => {
        if (settled) return;
        settled = true;
        resolve(ok);
      };
      try {
        const socket = this.createSocket(speechTranscribeWsUrl());
        this.socket = socket;
        socket.binaryType = 'arraybuffer';
        socket.onopen = () => {
          socket.send(sttStreamControl('start'));
          finish(true);
        };
        socket.onerror = () => finish(false);
        socket.onclose = () => {
          if (this.socket === socket) this.socket = null;
          finish(false);
        };
        socket.onmessage = (event) => {
          if (typeof event.data !== 'string') return;
          try {
            const parsed = parseSttStreamEvent(JSON.parse(event.data) as unknown);
            if (parsed.text) this.last = parsed.text;
            if (parsed.kind === 'partial' && parsed.text) onPartial?.(parsed.text);
          } catch {
          }
        };
      } catch {
        finish(false);
      }
    });
  }

  async sendChunk(blob: Blob): Promise<void> {
    if (this.socket?.readyState !== WebSocket.OPEN) return;
    this.socket.send(await blob.arrayBuffer());
  }

  async end(language = 'tr'): Promise<string> {
    const socket = this.socket;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      this.close();
      return this.last;
    }
    return new Promise((resolve) => {
      const timer = window.setTimeout(() => {
        this.close();
        resolve(this.last);
      }, 8_000);
      const previous = socket.onmessage;
      socket.onmessage = (event) => {
        previous?.call(socket, event);
        if (typeof event.data !== 'string') return;
        try {
          const parsed = parseSttStreamEvent(JSON.parse(event.data) as unknown);
          if (parsed.text) this.last = parsed.text;
          if (parsed.kind === 'final' || parsed.kind === 'error') {
            window.clearTimeout(timer);
            this.close();
            resolve(this.last);
          }
        } catch {
        }
      };
      socket.send(sttStreamControl('end', language));
    });
  }

  close(): void {
    if (this.socket && this.socket.readyState <= WebSocket.OPEN) this.socket.close();
    this.socket = null;
  }
}
