/**
 * Backend `/ws/host` köprüsü istemcisi.
 *
 * Electron main process bu bağlantıyı kurar ve:
 *  - backend'in gönderdiği `host_tool_request` mesajlarını çalıştırıp cevaplar,
 *  - `timeout_ms` / `host_tool_cancel` ile Open Interpreter tarzı süre+iptal uygular,
 *  - bağlanınca yetenek listesini (`host_capabilities`) ilan eder,
 *  - belirli aralıklarla gerçek Windows sistem metriklerini ve JSON ping'i push eder.
 *
 * Bağlantı koparsa üstel geri çekilme ile yeniden bağlanır.
 */

import { EventEmitter } from 'node:events';
import WebSocket from 'ws';

import { executeHostTool, hostCapabilityPayload, setHostCapabilitiesRefreshSink } from './host-tools';
import { hostT, hostText } from './host-i18n';
import { shouldGiveUpHostReconnect } from './host-tools/host-close';
import { formatHostError } from './host-tools/host-error';
import {
  shouldForceReconnectOnResume,
  shouldScheduleReconnectWhileAwake,
} from './host-tools/power-resume';
import { reconnectDelayMs } from './host-tools/reconnect-delay';
import { shouldGiveUpReconnectAfterGrace } from './host-tools/reconnect-grace';
import { shouldTerminateStaleSocket } from './host-tools/ws-liveness';
import { collectMetrics } from './host-tools/system';

/**
 * Continue abort / OI terminal.stop: iptalde de cevap gider, future asılı kalmaz.
 * https://github.com/continuedev/continue/blob/main/core/context/mcp/MCPConnection.ts
 */
export function buildHostToolResponse(
  requestId: string,
  outcome: { success: boolean; result: Record<string, unknown>; error: string | null },
  cancelled: boolean,
): Record<string, unknown> {
  const error = cancelled
    ? outcome.error && /iptal|cancelled|canceled/i.test(outcome.error)
      ? outcome.error
      : hostT('host.toolCancelled')
    : outcome.error;
  return {
    type: 'host_tool_response',
    request_id: requestId,
    success: cancelled ? false : outcome.success,
    result: cancelled ? { ...outcome.result, cancelled: true } : outcome.result,
    error,
    cancelled,
  };
}

const METRICS_INTERVAL_MS = 3000;
const PING_INTERVAL_MS = 20_000;

export interface HostBridgeState {
  connected: boolean;
  url: string;
  lastError: string | null;
  reconnectAttempts: number;
  inFlight: number;
  capabilitiesAnnounced: boolean;
}

/** Backend ile host arasındaki kalıcı WebSocket köprüsü. */
export class HostBridgeClient extends EventEmitter {
  private socket: WebSocket | null = null;
  private reconnectTimer: NodeJS.Timeout | null = null;
  private metricsTimer: NodeJS.Timeout | null = null;
  private pingTimer: NodeJS.Timeout | null = null;
  private attempts = 0;
  private stopped = true;
  /** ``start()`` çağrıldı mı? ``configure()`` bundan önce bağlantı açmamalı. */
  private started = false;
  private lastError: string | null = null;
  private baseUrl = '';
  private token = '';
  private appVersion = '0.0.0';
  private readonly inflight = new Map<string, AbortController>();
  private capabilitiesAnnounced = false;
  private suspended = false;
  private lastResumeAt: number | null = null;
  private lastAliveAt: number | null = null;
  private reconnectLoopStartAt: number | null = null;
  private reconnectGaveUp = false;

  /**
   * Bağlantı bilgilerini ayarlar.
   *
   * Yalnızca köprü zaten başlatılmışsa ve adres/token gerçekten değiştiyse
   * yeniden bağlanır. Aksi hâlde ``start()`` ile ikinci bir soket açılır;
   * backend eskisini kapatınca kapanan soketin ``close`` işleyicisi canlı
   * bağlantının zamanlayıcılarını temizler ve metrikler hiç akmaz.
   */
  configure(backendUrl: string, token: string, appVersion: string): void {
    const nextBase = backendUrl.replace(/\/+$/, '');
    const changed = nextBase !== this.baseUrl || token !== this.token;
    this.baseUrl = nextBase;
    this.token = token;
    this.appVersion = appVersion;
    if (changed && this.started) this.reconnect();
  }

  /** Anlık durum. */
  get state(): HostBridgeState {
    return {
      connected: this.socket?.readyState === WebSocket.OPEN,
      url: this.displayUrl(),
      lastError: this.lastError,
      reconnectAttempts: this.attempts,
      inFlight: this.inflight.size,
      capabilitiesAnnounced: this.capabilitiesAnnounced,
    };
  }

  /** Durum/IPC — token yok (Odysseus `_safe_url` / Sentry query strip). */
  private displayUrl(): string {
    if (!this.baseUrl) return '';
    return this.baseUrl.replace(/^http/, 'ws') + '/ws/host';
  }

  private wsUrl(): string {
    const url = this.displayUrl();
    if (!url) return '';
    const params = new URLSearchParams({ platform: process.platform, version: this.appVersion });
    if (this.token) params.set('token', this.token);
    return `${url}?${params.toString()}`;
  }

  /** Köprüyü başlatır (birden fazla çağrı güvenlidir). */
  start(): void {
    if (this.started && this.socket?.readyState === WebSocket.OPEN) return;
    this.started = true;
    this.stopped = false;
    this.resetReconnectGrace();
    setHostCapabilitiesRefreshSink(() => this.reannounceCapabilities());
    if (this.socket) {
      this.reconnect();
      return;
    }
    this.connect();
  }

  /**
   * API yeniden ayaktayken grace/timeout yüzünden kopmuş köprüyü zorla dener.
   * Sistem durumu / tepsi yoklaması buradan çağırır.
   */
  ensureConnected(): void {
    if (this.socket?.readyState === WebSocket.OPEN) return;
    if (!this.baseUrl) return;
    if (!this.started) {
      this.start();
      return;
    }
    this.stopped = false;
    this.resetReconnectGrace();
    this.reconnect();
  }

  /** Köprüyü durdurur. */
  stop(): void {
    this.stopped = true;
    this.started = false;
    setHostCapabilitiesRefreshSink(null);
    this.clearTimers();
    this.abortInflight();
    this.closeSocket();
  }

  /** MCP/ayar değişince Jan gibi ``tools/list`` yeteneklerini yeniden ilan eder. */
  reannounceCapabilities(): void {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.announceCapabilities();
    }
  }

  /** Uyku: ölü soket + backoff yakmasın. */
  handlePowerSuspend(): void {
    this.suspended = true;
    this.clearTimers();
    this.abortInflight();
    this.closeSocket();
  }

  /** Uyanınca backoff sıfır, hemen bağlan (VS Code onDidResumeOS). */
  handlePowerResume(now = Date.now()): boolean {
    if (!shouldForceReconnectOnResume(now, this.lastResumeAt)) return false;
    this.lastResumeAt = now;
    this.suspended = false;
    if (!this.started || this.stopped) return false;
    this.reconnect();
    return true;
  }

  /** Bağlantıyı yeniden kurar. */
  reconnect(): void {
    this.attempts = 0;
    this.resetReconnectGrace();
    this.clearTimers();
    this.abortInflight();
    this.closeSocket();
    this.started = true;
    this.stopped = false;
    this.connect();
  }

  /** Aktif soketi dinleyicilerini kaldırarak kapatır. */
  private closeSocket(): void {
    const socket = this.socket;
    this.socket = null;
    this.capabilitiesAnnounced = false;
    if (!socket) return;
    socket.removeAllListeners();
    try {
      socket.close(1000, hostText('Bağlantı yenileniyor', 'Refreshing the connection'));
    } catch {
    }
  }

  private abortInflight(): void {
    for (const controller of this.inflight.values()) {
      try {
        controller.abort();
      } catch {
      }
    }
    this.inflight.clear();
  }

  private clearTimers(): void {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    if (this.metricsTimer) clearInterval(this.metricsTimer);
    if (this.pingTimer) clearInterval(this.pingTimer);
    this.reconnectTimer = null;
    this.metricsTimer = null;
    this.pingTimer = null;
  }

  private connect(): void {
    if (this.stopped || this.suspended || !this.baseUrl || this.socket) return;

    const url = this.wsUrl();
    let socket: WebSocket;
    try {
      socket = new WebSocket(url, { handshakeTimeout: 8000 });
    } catch (error) {
      this.lastError = formatHostError(error).slice(0, 400);
      this.scheduleReconnect();
      return;
    }

    this.socket = socket;

    /** Olayın hâlâ güncel soketten geldiğini doğrular. */
    const isCurrent = (): boolean => this.socket === socket;

    socket.on('open', () => {
      if (!isCurrent()) return;
      this.attempts = 0;
      this.lastError = null;
      this.resetReconnectGrace();
      this.lastAliveAt = Date.now();
      this.announceCapabilities();
      this.emit('connection', this.state);
      this.startMetricsLoop();
      this.startPingLoop();
    });

    socket.on('pong', () => {
      if (!isCurrent()) return;
      this.lastAliveAt = Date.now();
    });

    socket.on('message', (raw) => {
      if (!isCurrent()) return;
      this.lastAliveAt = Date.now();
      void this.handleMessage(raw.toString());
    });

    socket.on('close', (code) => {
      if (!isCurrent()) return;
      this.clearTimers();
      this.abortInflight();
      this.socket = null;
      this.capabilitiesAnnounced = false;
      if (shouldGiveUpHostReconnect(Number(code))) {
        this.stopped = true;
        this.lastError = hostT('host.invalidToken');
      }
      this.emit('connection', this.state);
      if (this.suspended || this.stopped) return;
      this.scheduleReconnect();
    });

    socket.on('error', (error) => {
      if (!isCurrent()) return;
      this.lastError = formatHostError(error).slice(0, 400);
    });
  }

  private resetReconnectGrace(): void {
    this.reconnectLoopStartAt = null;
    this.reconnectGaveUp = false;
  }

  private scheduleReconnect(): void {
    if (!shouldScheduleReconnectWhileAwake(this.suspended, this.stopped) || this.reconnectTimer) {
      return;
    }
    if (this.reconnectGaveUp) return;
    if (this.reconnectLoopStartAt == null) this.reconnectLoopStartAt = Date.now();
    if (shouldGiveUpReconnectAfterGrace(this.reconnectLoopStartAt, Date.now())) {
      this.reconnectGaveUp = true;
      this.lastError = hostT('host.bridgeReconnectFail');
      this.emit('connection', this.state);
      return;
    }
    this.attempts += 1;
    const delay = reconnectDelayMs(this.attempts);
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }

  private startMetricsLoop(): void {
    if (this.metricsTimer) return;
    const push = async (): Promise<void> => {
      if (this.socket?.readyState !== WebSocket.OPEN) return;
      try {
        const payload = await collectMetrics();
        this.send({ type: 'host_metrics', payload });
      } catch {
      }
    };
    void push();
    this.metricsTimer = setInterval(() => void push(), METRICS_INTERVAL_MS);
  }

  private startPingLoop(): void {
    if (this.pingTimer) return;
    this.pingTimer = setInterval(() => {
      if (this.socket?.readyState !== WebSocket.OPEN) return;
      if (this.suspended) return;
      if (shouldTerminateStaleSocket(Date.now(), this.lastAliveAt)) {
        this.lastError = hostT('host.bridgeSilent');
        try {
          this.socket.terminate();
        } catch {
        }
        return;
      }
      try {
        this.socket.ping();
        this.send({ type: 'ping' });
      } catch {
      }
    }, PING_INTERVAL_MS);
  }

  private announceCapabilities(): void {
    this.send(hostCapabilityPayload(this.appVersion));
    this.capabilitiesAnnounced = true;
  }

  private send(payload: Record<string, unknown>): void {
    if (this.socket?.readyState !== WebSocket.OPEN) return;
    try {
      this.socket.send(JSON.stringify(payload));
    } catch (error) {
      this.lastError = formatHostError(error).slice(0, 400);
    }
  }

  private async handleMessage(raw: string): Promise<void> {
    let message: Record<string, unknown>;
    try {
      message = JSON.parse(raw) as Record<string, unknown>;
    } catch {
      return;
    }

    const type = String(message.type ?? '');

    if (type === 'host_tool_cancel') {
      const requestId = String(message.request_id ?? '');
      this.inflight.get(requestId)?.abort();
      return;
    }

    if (type === 'host_tool_request') {
      const requestId = String(message.request_id ?? '');
      const toolName = String(message.tool_name ?? '');
      const args = (message.arguments ?? {}) as Record<string, unknown>;
      const timeoutMs = Number(message.timeout_ms);
      const controller = new AbortController();
      if (requestId) this.inflight.set(requestId, controller);

      this.emit('tool', { toolName, args });
      try {
        const outcome = await executeHostTool(toolName, args, {
          timeoutMs: Number.isFinite(timeoutMs) ? timeoutMs : undefined,
          signal: controller.signal,
        });
        this.send(buildHostToolResponse(requestId, outcome, controller.signal.aborted));
      } finally {
        this.inflight.delete(requestId);
      }
      return;
    }

    if (type === 'host_bridge_ready') {
      if (!this.capabilitiesAnnounced) this.announceCapabilities();
      this.emit('ready');
    }
  }

  /** Backend'e hata bildirir (arayüzün "son hata" alanına düşer). */
  reportError(message: string): void {
    this.send({ type: 'host_error', message: message.slice(0, 500) });
  }
}
