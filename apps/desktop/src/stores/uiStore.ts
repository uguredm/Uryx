/** Arayüz durumu: aktif görünüm, paneller, bildirimler. */

import { create } from 'zustand';

import { formatQuotedMessage } from '@/lib/composerQuote';

export type ViewName =
  'chat' | 'history' | 'memory' | 'documents' | 'tools' | 'system' | 'settings';

export interface Toast {
  id: string;
  kind: 'info' | 'success' | 'warning' | 'error';
  message: string;
}

export type VoiceState = 'idle' | 'listening' | 'transcribing';

interface UIState {
  view: ViewName;
  rightPanelOpen: boolean;
  sidebarCollapsed: boolean;
  toasts: Toast[];
  voiceState: VoiceState;
  voiceLevel: number;
  voiceToggleRequest: number;
  historySearchTick: number;
  composerQuoteTick: number;
  composerQuote: string;
  composerFocusTick: number;
  sttPartial: string;
  setView: (view: ViewName) => void;
  toggleRightPanel: () => void;
  toggleSidebar: () => void;
  pushToast: (kind: Toast['kind'], message: string) => void;
  dismissToast: (id: string) => void;
  setVoiceState: (voiceState: VoiceState) => void;
  setVoiceLevel: (voiceLevel: number) => void;
  requestVoiceToggle: () => void;
  openHistorySearch: () => void;
  quoteToComposer: (text: string) => void;
  focusComposer: () => void;
  setSttPartial: (sttPartial: string) => void;
}

let toastCounter = 0;

export const useUIStore = create<UIState>((set) => ({
  view: 'chat',
  rightPanelOpen: true,
  sidebarCollapsed: false,
  toasts: [],
  voiceState: 'idle',
  voiceLevel: 0,
  voiceToggleRequest: 0,
  historySearchTick: 0,
  composerQuoteTick: 0,
  composerQuote: '',
  composerFocusTick: 0,
  sttPartial: '',

  setView: (view) => set({ view }),
  toggleRightPanel: () => set((state) => ({ rightPanelOpen: !state.rightPanelOpen })),
  toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),

  pushToast: (kind, message) => {
    toastCounter += 1;
    const id = `toast-${toastCounter}`;
    set((state) => ({ toasts: [...state.toasts, { id, kind, message }].slice(-4) }));
    window.setTimeout(
      () => {
        set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) }));
      },
      kind === 'error' ? 8000 : 4000,
    );
  },

  dismissToast: (id) => set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),
  setVoiceState: (voiceState) => set({ voiceState }),
  setVoiceLevel: (voiceLevel) => set({ voiceLevel }),
  requestVoiceToggle: () => set((state) => ({ voiceToggleRequest: state.voiceToggleRequest + 1 })),
  openHistorySearch,
  quoteToComposer,
  focusComposer,
  setSttPartial: (sttPartial) => set({ sttPartial }),
}));

/** Open WebUI Ctrl+K — geçmiş aramasını açar ve kutuya odaklanır. */
export function openHistorySearch(): void {
  useUIStore.setState((state) => ({
    view: 'history',
    historySearchTick: state.historySearchTick + 1,
  }));
}

/** Chatbox `setQuote` — alıntıyı besteciye bırakır, kutuya odaklanır. */
export function quoteToComposer(text: string): boolean {
  const quote = formatQuotedMessage(text);
  if (!quote) return false;
  useUIStore.setState((state) => ({
    view: 'chat',
    composerQuote: quote,
    composerQuoteTick: state.composerQuoteTick + 1,
  }));
  return true;
}

/** NextChat Shift+Esc — sohbet görünümü + kutu odağı. */
export function focusComposer(): void {
  useUIStore.setState((state) => ({
    view: 'chat',
    composerFocusTick: state.composerFocusTick + 1,
  }));
}
