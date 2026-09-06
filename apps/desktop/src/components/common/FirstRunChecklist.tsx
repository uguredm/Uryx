/**
 * AnythingLLM / Jan: ilk açılışta yığın hazır mı, net maddeler.
 * Ses odaklı HUD'u kilitlemez; kapatılabilir.
 */

import { useMemo, useState } from 'react';
import { Check, Circle, X } from 'lucide-react';

import { useSystemStore } from '@/hooks/useSystemStatus';
import {
  buildReadiness,
  dismissFirstRun,
  isFirstRunDismissed,
  shouldShowFirstRun,
} from '@/lib/firstRun';
import { serviceDisplayName } from '@/lib/apiText';
import { useI18n } from '@/lib/i18n';
import { useChatStore } from '@/stores/chatStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { useUIStore } from '@/stores/uiStore';

export function FirstRunChecklist(): JSX.Element | null {
  const [dismissed, setDismissed] = useState(isFirstRunDismissed);
  const { language, t } = useI18n();
  const connection = useChatStore((state) => state.connection);
  const status = useSystemStore((state) => state.status);
  const mcpEnabled = useSettingsStore((state) => state.settings.mcpEnabled);
  const mcpServerCount = useSettingsStore((state) => state.settings.mcpServers.length);
  const setView = useUIStore((state) => state.setView);

  const downKey = (status?.services ?? [])
    .filter((service) => service.state === 'down' || service.state === 'degraded')
    .map((service) => serviceDisplayName(service.name, service.display_name, language))
    .join('|');

  const items = useMemo(
    () =>
      buildReadiness({
        chatOpen: connection === 'open',
        modelLoaded: status ? status.model.loaded : null,
        downServices: downKey ? downKey.split('|') : [],
        mcpEnabled,
        mcpServerCount,
        language,
      }),
    [connection, status, downKey, mcpEnabled, mcpServerCount, language],
  );

  if (!shouldShowFirstRun(items, dismissed)) return null;

  return (
    <aside className="first-run-card" aria-label={t('firstRun.aria')}>
      <div className="first-run-card__head">
        <p>{t('firstRun.title')}</p>
        <button
          type="button"
          onClick={() => {
            dismissFirstRun();
            setDismissed(true);
          }}
          aria-label={t('firstRun.close')}
        >
          <X size={14} />
        </button>
      </div>
      <ul>
        {items.map((item) => (
          <li key={item.id} className={item.ready ? 'is-ready' : 'is-wait'}>
            {item.ready ? <Check size={13} /> : <Circle size={13} />}
            <div>
              <strong>{item.label}</strong>
              <span>{item.hint}</span>
            </div>
            {!item.ready && item.action && (
              <button
                type="button"
                onClick={() => {
                  if (item.action) setView(item.action);
                }}
              >
                {t('firstRun.open')}
              </button>
            )}
          </li>
        ))}
      </ul>
    </aside>
  );
}
