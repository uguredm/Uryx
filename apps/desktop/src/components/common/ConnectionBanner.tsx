/**
 * Yerel yığın durumu — Open WebUI / Jan: bağlantı kopunca gri ekran yok,
 * yeniden bağlan ve servis çipleri net.
 */

import { RefreshCw } from 'lucide-react';

import { useSystemStore } from '@/hooks/useSystemStatus';
import { serviceDisplayName } from '@/lib/apiText';
import { useI18n } from '@/lib/i18n';
import { useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';

export function ConnectionBanner(): JSX.Element | null {
  const connection = useChatStore((state) => state.connection);
  const reconnect = useChatStore((state) => state.reconnect);
  const streamDropped = useChatStore((state) => state.streamDropped);
  const generating = useChatStore((state) => state.generating);
  const streamContent = useChatStore((state) => state.streamContent);
  const status = useSystemStore((state) => state.status);
  const setView = useUIStore((state) => state.setView);
  const { t, language } = useI18n();

  if (connection !== 'open') {
    const connecting = connection === 'connecting';
    const keepPartial = streamDropped && (generating || Boolean(streamContent.trim()));
    return (
      <div className="connection-banner is-offline" role="status">
        <span>
          {keepPartial
            ? t('banner.partial')
            : connecting
              ? t('banner.connecting')
              : t('banner.offline')}
        </span>
        <button type="button" onClick={() => reconnect()} disabled={connecting}>
          <RefreshCw size={12} />
          {t('banner.reconnect')}
        </button>
        <button type="button" onClick={() => setView('system')}>
          {t('banner.services')}
        </button>
      </div>
    );
  }

  const down = (status?.services ?? []).filter(
    (service) => service.state === 'down' || service.state === 'degraded',
  );
  const modelDown = Boolean(status && !status.model.loaded);
  if (!modelDown && down.length === 0) return null;

  return (
    <div className="connection-banner is-degraded" role="status">
      <span>
        {modelDown
          ? t('banner.model')
          : t('banner.degraded')}
      </span>
      <div className="connection-banner__chips">
        {modelDown && <span className="connection-chip">{t('banner.modelChip')}</span>}
        {down.slice(0, 4).map((service) => (
          <span key={service.name} className="connection-chip">
            {serviceDisplayName(service.name, service.display_name, language)}
          </span>
        ))}
      </div>
      <button type="button" onClick={() => setView('system')}>
        {t('banner.status')}
      </button>
    </div>
  );
}
