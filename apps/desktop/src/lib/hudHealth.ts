/** HUD sessiz sağlık — ConnectionBanner predikatlarının özeti. */

import type { SystemStatus } from '@shared/api';
import type { UiLanguage } from '@shared/settings';

import type { ConnectionStatus } from '@/lib/chatSocket';
import { translate } from '@/lib/i18n';
import { serviceDisplayName } from '@/lib/apiText';

export type HudHealthKind = 'offline' | 'degraded';

export interface HudHealthIssue {
  kind: HudHealthKind;
  label: string;
  detail: string;
  dot: 'down' | 'degraded' | 'starting';
}

export function describeHudHealth(
  connection: ConnectionStatus,
  status: SystemStatus | null,
  language: UiLanguage = 'en',
): HudHealthIssue | null {
  if (connection !== 'open') {
    const connecting = connection === 'connecting';
    return {
      kind: 'offline',
      label: translate(language, connecting ? 'hud.health.connecting' : 'hud.health.offline'),
      detail: translate(
        language,
        connecting ? 'hud.health.connectingDetail' : 'hud.health.offlineDetail',
      ),
      dot: connecting ? 'starting' : 'down',
    };
  }

  const down = (status?.services ?? []).filter(
    (service) => service.state === 'down' || service.state === 'degraded',
  );
  const modelDown = Boolean(status && !status.model.loaded);
  if (!modelDown && down.length === 0) return null;

  return {
    kind: 'degraded',
    label: modelDown
      ? translate(language, 'hud.health.model')
      : serviceDisplayName(
          down[0]?.name ?? 'service',
          down[0]?.display_name ?? translate(language, 'hud.health.service'),
          language,
        ).toLocaleUpperCase(language === 'tr' ? 'tr-TR' : 'en-US'),
    detail: translate(language, modelDown ? 'hud.health.modelDetail' : 'hud.health.serviceDetail'),
    dot: 'degraded',
  };
}
