/**
 * `/ws/system` üzerinden yayınlanan sistem durumunu dinler.
 *
 * WebSocket kurulamazsa REST üzerinden periyodik yoklamaya düşer; böylece
 * sistem ekranı her hâlükârda veri gösterir.
 */

import { useEffect } from 'react';
import { create } from 'zustand';
import type { SystemStatus } from '@shared/api';

import { api } from '@/lib/api';
import { useSettingsStore } from '@/stores/settingsStore';

export interface ComposeProgress {
  phase: string;
  message: string;
  at: number;
}

interface SystemState {
  status: SystemStatus | null;
  connected: boolean;
  lastUpdate: number;
  error: string | null;
  composeProgress: ComposeProgress | null;
  setStatus: (status: SystemStatus) => void;
  setConnected: (connected: boolean) => void;
  setError: (error: string | null) => void;
  setComposeProgress: (progress: ComposeProgress | null) => void;
}

export const useSystemStore = create<SystemState>((set) => ({
  status: null,
  connected: false,
  lastUpdate: 0,
  error: null,
  composeProgress: null,
  setStatus: (status) => set({ status, lastUpdate: Date.now(), error: null }),
  setConnected: (connected) => set({ connected }),
  setError: (error) => set({ error }),
  setComposeProgress: (composeProgress) => set({ composeProgress }),
}));

const RECONNECT_MS = 4000;
const POLL_MS = 6000;

/** Sistem durumu aboneliğini kurar (uygulamada bir kez çağrılmalı). */
export function useSystemStatus(): void {
  const { settings, loaded } = useSettingsStore();

  useEffect(() => {
    if (!loaded) return;

    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let pollTimer: number | null = null;
    let disposed = false;

    const { setStatus, setConnected, setError } = useSystemStore.getState();

    /** REST yoklaması (WebSocket yoksa). */
    const startPolling = (): void => {
      if (pollTimer !== null || disposed) return;
      const poll = async (): Promise<void> => {
        try {
          setStatus(await api.system.status());
        } catch (error) {
          setError(error instanceof Error ? error.message : String(error));
        }
      };
      void poll();
      pollTimer = window.setInterval(() => void poll(), POLL_MS);
    };

    const stopPolling = (): void => {
      if (pollTimer !== null) {
        window.clearInterval(pollTimer);
        pollTimer = null;
      }
    };

    const connect = (): void => {
      if (disposed) return;

      const wsBase = settings.backendUrl.replace(/^http/, 'ws').replace(/\/+$/, '');
      const params = settings.localToken
        ? `?token=${encodeURIComponent(settings.localToken)}`
        : '';

      try {
        socket = new WebSocket(`${wsBase}/ws/system${params}`);
      } catch {
        startPolling();
        return;
      }

      socket.onopen = () => {
        setConnected(true);
        stopPolling();
      };

      socket.onmessage = (message) => {
        try {
          const parsed = JSON.parse(message.data as string) as {
            type?: string;
            payload?: SystemStatus;
          };
          if (parsed.type === 'system_update' && parsed.payload) setStatus(parsed.payload);
        } catch {
        }
      };

      socket.onerror = () => setConnected(false);

      socket.onclose = () => {
        setConnected(false);
        socket = null;
        if (disposed) return;
        startPolling();
        reconnectTimer = window.setTimeout(connect, RECONNECT_MS);
      };
    };

    connect();

    return () => {
      disposed = true;
      stopPolling();
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      if (socket) {
        socket.onclose = null;
        socket.close();
      }
      useSystemStore.getState().setConnected(false);
    };
  }, [loaded, settings.backendUrl, settings.localToken]);
}
