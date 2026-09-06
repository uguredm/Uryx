import { useEffect, useState, type ReactNode } from 'react';
import { Archive, Brain, Database, FileText, MessageSquare, Settings, Wrench } from 'lucide-react';

import { AccentThemePicker } from '@/components/common/AccentThemePicker';
import { HudHealthChip } from '@/components/hud/HudHealthChip';
import { useSystemStore } from '@/hooks/useSystemStatus';
import { cn } from '@/lib/cn';
import { useI18n, type MessageKey } from '@/lib/i18n';
import { useSettingsStore } from '@/stores/settingsStore';
import { type ViewName, useUIStore } from '@/stores/uiStore';

const ITEMS: Array<{ view: ViewName; labelKey: MessageKey; code: string; icon: typeof Archive }> = [
  { view: 'chat', labelKey: 'ws.nav.chat', code: '01', icon: MessageSquare },
  { view: 'history', labelKey: 'hud.nav.history', code: '02', icon: Archive },
  { view: 'memory', labelKey: 'hud.nav.memory', code: '03', icon: Brain },
  { view: 'documents', labelKey: 'hud.nav.documents', code: '04', icon: FileText },
  { view: 'tools', labelKey: 'hud.nav.tools', code: '05', icon: Wrench },
  { view: 'system', labelKey: 'hud.nav.system', code: '06', icon: Database },
  { view: 'settings', labelKey: 'hud.nav.settings', code: '07', icon: Settings },
];

export function UryxWorkspace({ children }: { children: ReactNode }): JSX.Element {
  const [now, setNow] = useState(() => new Date());
  const view = useUIStore((state) => state.view);
  const setView = useUIStore((state) => state.setView);
  const status = useSystemStore((state) => state.status);
  const connected = useSystemStore((state) => state.connected);
  const modelName = useSettingsStore((state) => state.settings.modelName);
  const accentTheme = useSettingsStore((state) => state.settings.accentTheme);
  const updateSettings = useSettingsStore((state) => state.update);
  const { t, locale } = useI18n();

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const active = ITEMS.find((item) => item.view === view) ?? ITEMS[0];
  const ActiveIcon = active.icon;
  const serviceUp = status?.services.filter((service) => service.state === 'up').length ?? 0;

  return (
    <div className="uryx-workspace">
      <header className="uryx-workspace__header">
        <button type="button" className="hud-brand" onClick={() => setView('chat')}>
          <span className="hud-brand__mark">U</span>
          <div>
            <strong>U.R.Y.X</strong>
            <span>{t('ws.brand.sub')}</span>
          </div>
        </button>
        <div className="uryx-workspace__title">
          <ActiveIcon size={15} />
          <div>
            <span>{t('ws.module', { code: active.code })}</span>
            <strong>{t(active.labelKey)}</strong>
          </div>
        </div>
        <div className="hud-header-clock">
          <HudHealthChip />
          <AccentThemePicker
            variant="hud"
            value={accentTheme}
            onChange={(accent) => {
              void updateSettings({ accentTheme: accent });
            }}
          />
          <span className="hud-header-model" title={status?.model.model_id ?? modelName}>
            {status?.model.model_id ?? modelName}
          </span>
          <strong>
            {now.toLocaleTimeString(locale, {
              hour: '2-digit',
              minute: '2-digit',
              second: '2-digit',
            })}
          </strong>
        </div>
      </header>

      <aside className="uryx-workspace__nav">
        <div className="uryx-workspace__nav-label">{t('ws.nav')}</div>
        {ITEMS.map(({ view: itemView, labelKey, code, icon: Icon }) => (
          <button
            key={itemView}
            type="button"
            className={cn(itemView === view && 'is-active')}
            onClick={() => setView(itemView)}
          >
            <span>{code}</span>
            <Icon size={14} />
            <strong>{t(labelKey)}</strong>
          </button>
        ))}
        <div className="uryx-workspace__telemetry">
          <span>{t('ws.services')}</span>
          <strong>
            {serviceUp.toString().padStart(2, '0')} /{' '}
            {(status?.services.length ?? 0).toString().padStart(2, '0')}
          </strong>
          <i className={connected ? 'is-online' : ''}>
            {connected ? t('ws.online') : t('ws.reconnect')}
          </i>
        </div>
      </aside>

      <main className="uryx-workspace__content scroll-area">{children}</main>
      <footer className="uryx-workspace__footer">
        <span>{t('ws.footer.channel')}</span>
        <span>{t('ws.footer.esc')}</span>
        <strong className={connected ? 'is-online' : ''}>
          {t('ws.footer.sys', {
            state: connected ? t('hud.footer.online') : t('hud.terminal.offline'),
          })}
        </strong>
      </footer>
    </div>
  );
}
