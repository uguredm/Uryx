import { useSystemStore } from '@/hooks/useSystemStatus';
import { describeHudHealth } from '@/lib/hudHealth';
import { useChatStore } from '@/stores/chatStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { useUIStore } from '@/stores/uiStore';

/** HUD’da sessiz sağlık; tam ConnectionBanner sohbet görünümünde yok. */
export function HudHealthChip(): JSX.Element | null {
  const connection = useChatStore((state) => state.connection);
  const status = useSystemStore((state) => state.status);
  const language = useSettingsStore((state) => state.settings.language);
  const setView = useUIStore((state) => state.setView);
  const issue = describeHudHealth(connection, status, language);
  if (!issue) return null;

  return (
    <button
      type="button"
      className="hud-health-chip"
      title={issue.detail}
      onClick={() => setView('system')}
    >
      <span className={`hud-status-dot is-${issue.dot}`} aria-hidden />
      {issue.label}
    </button>
  );
}
