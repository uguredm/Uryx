/**
 * `/ws/chat` WebSocket istemcisi.
 *
 * Otomatik yeniden bağlanma (üstel geri çekilme) ve tip güvenli olay dağıtımı
 * sağlar. Bağlantı kopukken gönderilen mesajlar kuyruğa alınmaz; arayüz
 * kullanıcıya "bağlantı yok" durumunu gösterir.
 */

import type { WSClientEvent, WSServerEvent } from '@shared/ws';

import { tNow } from '@/lib/tNow';
import { getUiLanguage } from '@/lib/uiLocale';

export type ConnectionStatus = 'connecting' | 'open' | 'closed' | 'error';

export interface ChatSocketHandlers {
  onEvent: (event: WSServerEvent) => void;
  onStatus: (status: ConnectionStatus, detail?: string) => void;
}

const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 15_000;
const HEARTBEAT_MS = 25_000;

/** Sohbet WebSocket bağlantısı. */
export class ChatSocket {
  private socket: WebSocket | null = null;
  private reconnectTimer: number | null = null;
  private heartbeatTimer: number | null = null;
  private attempts = 0;
  private closedByUser = false;
  private url = '';

  constructor(private readonly handlers: ChatSocketHandlers) {}

  /** Bağlantıyı açar. */
  connect(baseUrl: string, token: string): void {
    this.closedByUser = false;
    const wsBase = baseUrl.replace(/^http/, 'ws').replace(/\/+$/, '');
    const params = new URLSearchParams();
    if (token) params.set('token', token);
    params.set('lang', getUiLanguage());
    const nextUrl = `${wsBase}/ws/chat?${params.toString()}`;

    if (this.socket && this.url === nextUrl && this.socket.readyState <= WebSocket.OPEN) return;
    this.url = nextUrl;
    this.close(false);
    this.open();
  }

  private open(): void {
    if (this.closedByUser || !this.url) return;
    this.handlers.onStatus('connecting');

    let socket: WebSocket;
    try {
      socket = new WebSocket(this.url);
    } catch (error) {
      this.handlers.onStatus('error', String(error));
      this.scheduleReconnect();
      return;
    }

    this.socket = socket;

    socket.onopen = () => {
      this.attempts = 0;
      this.handlers.onStatus('open');
      this.startHeartbeat();
    };

    socket.onmessage = (message) => {
      try {
        const parsed = JSON.parse(message.data as string) as WSServerEvent;
        if (parsed && typeof parsed === 'object' && 'type' in parsed) {
          if (parsed.type !== 'pong') this.handlers.onEvent(parsed);
        }
      } catch {
      }
    };

    socket.onerror = () => {
      this.handlers.onStatus('error', tNow('api.wsError'));
    };

    socket.onclose = (event) => {
      this.stopHeartbeat();
      this.socket = null;
      if (event.code === 4401) {
        this.handlers.onStatus('error', tNow('api.wsToken'));
        this.closedByUser = true;
        return;
      }
      this.handlers.onStatus('closed');
      this.scheduleReconnect();
    };
  }

  private scheduleReconnect(): void {
    if (this.closedByUser || this.reconnectTimer !== null) return;
    this.attempts += 1;
    const delay = Math.min(RECONNECT_BASE_MS * 2 ** Math.min(this.attempts - 1, 4), RECONNECT_MAX_MS);
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this.open();
    }, delay);
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = window.setInterval(() => {
      this.send({ type: 'ping' });
    }, HEARTBEAT_MS);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer !== null) {
      window.clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  /** Bağlantı açık mı? */
  get isOpen(): boolean {
    return this.socket?.readyState === WebSocket.OPEN;
  }

  /**
   * Sunucuya olay gönderir.
   * @returns Gönderilebildiyse `true`.
   */
  send(event: WSClientEvent): boolean {
    if (this.socket?.readyState !== WebSocket.OPEN) return false;
    try {
      this.socket.send(JSON.stringify(event));
      return true;
    } catch {
      return false;
    }
  }

  /** Üstel beklemeyi sıfırlayıp hemen yeniden dener (Open WebUI reload). */
  reconnect(): void {
    this.closedByUser = false;
    this.attempts = 0;
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.close(false);
    this.open();
  }

  /** Bağlantıyı kapatır. */
  close(byUser = true): void {
    if (byUser) this.closedByUser = true;
    this.stopHeartbeat();
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.socket) {
      this.socket.onclose = null;
      this.socket.onerror = null;
      this.socket.onmessage = null;
      this.socket.onopen = null;
      try {
        this.socket.close();
      } catch {
      }
      this.socket = null;
    }
  }
}
