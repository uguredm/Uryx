/** Kayıt sırasında görünen ses seviyesi animasyonu. */

import { useI18n } from '@/lib/i18n';

const BAR_COUNT = 24;

export function VoiceIndicator({ level }: { level: number }): JSX.Element {
  const { t } = useI18n();
  const normalized = Math.max(0, Math.min(level, 1));

  return (
    <div className="mt-2 flex items-center justify-center gap-3">
      <span className="flex items-center gap-1.5 text-[11.5px] text-uryx-danger">
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-pulse-ring rounded-full bg-uryx-danger" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-uryx-danger" />
        </span>
        {t('voice.listening')}
      </span>

      <div className="flex h-6 items-center gap-[3px]" aria-hidden>
        {Array.from({ length: BAR_COUNT }, (_, index) => {
          const distance = Math.abs(index - (BAR_COUNT - 1) / 2) / ((BAR_COUNT - 1) / 2);
          const weight = 1 - distance * 0.65;
          const height = Math.max(3, normalized * 24 * weight * (0.75 + Math.random() * 0.5));
          return (
            <span
              key={index}
              className="w-[3px] rounded-full bg-uryx-accent transition-all duration-100"
              style={{ height: `${height}px`, opacity: 0.45 + normalized * 0.55 }}
            />
          );
        })}
      </div>

      <span className="text-[11px] text-slate-600">{t('voice.autoSend')}</span>
    </div>
  );
}
