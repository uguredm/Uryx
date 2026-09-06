/** HUD sohbet çubuğundaki araç / belge / düşün / ses anahtarları. */

import type { AppSettings } from '@shared/settings';

import { useI18n, type MessageKey } from '@/lib/i18n';

export type HudToggleKey = 'toolsEnabled' | 'ragEnabled' | 'thinkingMode' | 'ttsEnabled';

const OPTIONS: Array<{ key: HudToggleKey; labelKey: MessageKey }> = [
  { key: 'toolsEnabled', labelKey: 'hud.toggle.tools' },
  { key: 'ragEnabled', labelKey: 'hud.toggle.rag' },
  { key: 'thinkingMode', labelKey: 'hud.toggle.think' },
  { key: 'ttsEnabled', labelKey: 'hud.toggle.voice' },
];

export function HudTerminalOptions({
  settings,
  onUpdate,
  stopSpeech,
}: {
  settings: Pick<AppSettings, HudToggleKey>;
  onUpdate: (patch: Partial<AppSettings>) => void | Promise<void>;
  stopSpeech: () => void;
}): JSX.Element {
  const { t } = useI18n();
  return (
    <div className="hud-terminal-options">
      {OPTIONS.map((option) => {
        const active = settings[option.key];
        const label = t(option.labelKey);
        return (
          <button
            key={option.key}
            type="button"
            className={active ? 'is-active' : undefined}
            aria-pressed={active}
            aria-label={label}
            onClick={() => {
              if (option.key === 'ttsEnabled' && settings.ttsEnabled) stopSpeech();
              void onUpdate({ [option.key]: !active });
            }}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}
