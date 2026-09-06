/**
 * Yeşil / mavi vurgu seçici — `html[data-accent]`.
 * Ayarlar: kartlar. HUD: üst çubukta anında uygulanır, electron-store’a yazılır.
 */

import { ACCENT_THEMES, type AccentTheme } from '@shared/settings';

import { cn } from '@/lib/cn';
import { useI18n } from '@/lib/i18n';
import {
  ACCENT_THEME_SWATCHES,
  cycleAccentTheme,
} from '@/lib/theme';

export function AccentThemePicker({
  value,
  onChange,
  variant = 'settings',
}: {
  value: AccentTheme;
  onChange: (accent: AccentTheme) => void;
  variant?: 'settings' | 'hud';
}): JSX.Element {
  const { t } = useI18n();
  const accentLabel = (accent: AccentTheme): string =>
    t(accent === 'blue' ? 'settings.accent.blue' : 'settings.accent.green');
  const accentHint = (accent: AccentTheme): string =>
    t(accent === 'blue' ? 'settings.accent.blueHint' : 'settings.accent.greenHint');
  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>): void => {
    if (
      event.key === 'ArrowLeft' ||
      event.key === 'ArrowRight' ||
      event.key === 'ArrowUp' ||
      event.key === 'ArrowDown'
    ) {
      event.preventDefault();
      onChange(cycleAccentTheme(value));
    }
  };

  if (variant === 'hud') {
    return (
      <div
        className="hud-accent-switch"
        role="radiogroup"
        aria-label={t('settings.accent')}
        onKeyDown={onKeyDown}
      >
        {ACCENT_THEMES.map((accent) => {
          const selected = value === accent;
          const swatch = ACCENT_THEME_SWATCHES[accent];
          return (
            <button
              key={accent}
              type="button"
              role="radio"
              aria-checked={selected}
              aria-label={accentLabel(accent)}
              title={accentHint(accent)}
              className={selected ? 'is-active' : undefined}
              onClick={() => onChange(accent)}
            >
              <span
                className="hud-accent-switch__swatch"
                style={{ background: `linear-gradient(135deg, ${swatch.from}, ${swatch.to})` }}
                aria-hidden
              />
            </button>
          );
        })}
      </div>
    );
  }

  return (
    <div
      className="grid grid-cols-2 gap-2"
      role="radiogroup"
      aria-label={t('settings.accent')}
      onKeyDown={onKeyDown}
    >
      {ACCENT_THEMES.map((accent) => {
        const selected = value === accent;
        const swatch = ACCENT_THEME_SWATCHES[accent];
        return (
          <button
            key={accent}
            type="button"
            role="radio"
            aria-checked={selected}
            aria-label={accentLabel(accent)}
            onClick={() => onChange(accent)}
            className={cn(
              'flex items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors',
              selected
                ? 'border-uryx-accent bg-uryx-accent/10'
                : 'border-uryx-border bg-uryx-panel/40 hover:border-uryx-accent/40',
            )}
          >
            <span
              className="h-8 w-8 shrink-0 rounded-md border border-white/10"
              style={{ background: `linear-gradient(135deg, ${swatch.from}, ${swatch.to})` }}
              aria-hidden
            />
            <span className="min-w-0">
              <span className="block text-[13px] font-medium text-slate-100">
                {accentLabel(accent)}
              </span>
              <span className="block text-[11px] text-slate-500">{accentHint(accent)}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
