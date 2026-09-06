/** Uygulama kabuğu: sol menü, ana içerik, sağ panel, modal ve bildirimler. */

import { useEffect } from 'react';

import { UryxWorkspace } from '@/components/layout/UryxWorkspace';
import { ToastStack } from '@/components/common/ToastStack';
import { UpdateModal } from '@/components/common/UpdateModal';
import { ToolConfirmModal } from '@/components/chat/ToolConfirmModal';
import { UryxDashboard } from '@/components/views/UryxDashboard';
import { HistoryView } from '@/components/views/HistoryView';
import { MemoryView } from '@/components/views/MemoryView';
import { DocumentsView } from '@/components/views/DocumentsView';
import { ToolsView } from '@/components/views/ToolsView';
import { SystemView } from '@/components/views/SystemView';
import { SettingsView } from '@/components/views/SettingsView';
import { ConnectionBanner } from '@/components/common/ConnectionBanner';
import { FirstRunChecklist } from '@/components/common/FirstRunChecklist';
import { useSystemStatus, useSystemStore } from '@/hooks/useSystemStatus';
import { applyAccentTheme } from '@/lib/theme';
import { translate } from '@/lib/i18n';
import { useChatStore } from '@/stores/chatStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { isEditableTarget, matchChatShortcut } from '@/lib/chatShortcuts';
import { focusComposer, openHistorySearch, useUIStore } from '@/stores/uiStore';

/** Aktif görünümü render eder. */
function ActiveView(): JSX.Element {
  const view = useUIStore((state) => state.view);

  switch (view) {
    case 'history':
      return <HistoryView />;
    case 'memory':
      return <MemoryView />;
    case 'documents':
      return <DocumentsView />;
    case 'tools':
      return <ToolsView />;
    case 'system':
      return <SystemView />;
    case 'settings':
      return <SettingsView />;
    default:
      return <SystemView />;
  }
}

export function App(): JSX.Element {
  const { settings, loaded, load } = useSettingsStore();
  const connect = useChatStore((state) => state.connect);
  const disconnect = useChatStore((state) => state.disconnect);
  const setVolume = useChatStore((state) => state.setVolume);
  const newConversation = useChatStore((state) => state.newConversation);
  const setView = useUIStore((state) => state.setView);
  const pushToast = useUIStore((state) => state.pushToast);
  const view = useUIStore((state) => state.view);

  useSystemStatus();

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    document.documentElement.lang = settings.language === 'tr' ? 'tr' : 'en';
  }, [settings.language]);

  useEffect(() => {
    if (!loaded) return;
    connect(settings.backendUrl, settings.localToken);
    return () => disconnect();
  }, [loaded, settings.backendUrl, settings.localToken, connect, disconnect]);

  useEffect(() => {
    const onPageHide = (): void => {
      useChatStore.getState().cancel();
    };
    window.addEventListener('pagehide', onPageHide);
    return () => window.removeEventListener('pagehide', onPageHide);
  }, []);

  useEffect(() => {
    applyAccentTheme(settings.accentTheme);
  }, [settings.accentTheme]);

  useEffect(() => {
    setVolume(settings.ttsVolume);
  }, [settings.ttsVolume, setVolume]);

  useEffect(() => {
    const bridge = window.uryx;
    if (!bridge) return;

    const unsubscribers = [
      bridge.on('tray:newChat', () => {
        newConversation();
        setView('chat');
      }),
      bridge.on('tray:openSettings', () => setView('settings')),
      bridge.on('tray:openSystem', () => setView('system')),
      bridge.on('app:error', (payload) => {
        const message = (payload as { message?: string })?.message;
        if (message) pushToast('error', message);
      }),
      bridge.on('host:connectionChanged', (payload) => {
        const state = payload as { connected?: boolean };
        if (state?.connected === false) {
          pushToast(
            'warning',
            translate(settings.language, 'toast.hostBridge'),
          );
        }
      }),
      bridge.on('services:progress', (payload) => {
        const item = payload as { phase?: string; message?: string };
        const phase = String(item.phase ?? '');
        if (phase === 'done' || phase === 'idle') {
          useSystemStore.getState().setComposeProgress(null);
          return;
        }
        if (item?.message) {
          useSystemStore.getState().setComposeProgress({
            phase,
            message: String(item.message),
            at: Date.now(),
          });
        }
      }),
    ];

    return () => unsubscribers.forEach((off) => off());
  }, [newConversation, setView, pushToast, settings.language]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        if (isEditableTarget(event.target)) return;
        event.preventDefault();
        openHistorySearch();
        return;
      }

      const shortcut = matchChatShortcut(event);
      if (!shortcut) return;
      if (useChatStore.getState().pendingConfirmation) return;
      if (shortcut === 'returnChat' && isEditableTarget(event.target)) return;

      event.preventDefault();
      if (shortcut === 'newChat') {
        newConversation();
        setView('chat');
        return;
      }
      if (shortcut === 'focusComposer') {
        focusComposer();
        return;
      }
      if (useUIStore.getState().view !== 'chat') setView('chat');
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [newConversation, setView]);

  if (!loaded) {
    return (
      <div className="flex h-full items-center justify-center bg-uryx-bg">
        <div className="flex flex-col items-center gap-3">
          <div className="h-10 w-10 animate-spin rounded-full border-2 border-uryx-border border-t-uryx-accent" />
          <p className="text-sm text-slate-400">{translate(settings.language, 'app.booting')}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full w-full flex-col overflow-hidden bg-uryx-bg">
      {view !== 'chat' && <ConnectionBanner />}
      {view !== 'chat' && <FirstRunChecklist />}
      <div className="min-h-0 flex-1 overflow-hidden">
        <div className={view === 'chat' ? 'h-full' : 'hidden'}>
          <UryxDashboard />
        </div>
        {view !== 'chat' && (
          <UryxWorkspace>
            <ActiveView />
          </UryxWorkspace>
        )}
      </div>
      <ToolConfirmModal />
      <UpdateModal />
      <ToastStack />
    </div>
  );
}
