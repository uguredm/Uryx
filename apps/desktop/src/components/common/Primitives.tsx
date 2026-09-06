/** Küçük, tekrar kullanılan arayüz parçaları. */

import type { ReactNode } from 'react';
import { Loader2 } from 'lucide-react';

import { cn } from '@/lib/cn';
import { useI18n } from '@/lib/i18n';

/** Ekran başlığı. */
export function ViewHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}): JSX.Element {
  return (
    <header className="flex shrink-0 items-start justify-between gap-4 border-b border-uryx-border px-6 py-4">
      <div className="min-w-0">
        <h1 className="text-lg font-semibold text-slate-100">{title}</h1>
        {description && <p className="mt-0.5 text-[13px] text-slate-500">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </header>
  );
}

/** Durum rozeti. */
export function StatusBadge({
  state,
  label,
}: {
  state: 'up' | 'down' | 'starting' | 'degraded' | 'unknown';
  label: string;
}): JSX.Element {
  const styles: Record<string, string> = {
    up: 'bg-uryx-ok/15 text-uryx-ok',
    down: 'bg-uryx-danger/15 text-uryx-danger',
    starting: 'bg-uryx-warn/15 text-uryx-warn',
    degraded: 'bg-uryx-warn/15 text-uryx-warn',
    unknown: 'bg-slate-700/40 text-slate-400',
  };
  const dot: Record<string, string> = {
    up: 'bg-uryx-ok',
    down: 'bg-uryx-danger',
    starting: 'bg-uryx-warn animate-pulse',
    degraded: 'bg-uryx-warn',
    unknown: 'bg-slate-500',
  };

  return (
    <span className={cn('badge', styles[state] ?? styles.unknown)}>
      <span className={cn('h-1.5 w-1.5 rounded-full', dot[state] ?? dot.unknown)} />
      {label}
    </span>
  );
}

/** Yüzde göstergeli ölçüm çubuğu. */
export function MetricBar({
  label,
  value,
  detail,
  tone = 'accent',
}: {
  label: string;
  value: number;
  detail?: string;
  tone?: 'accent' | 'warn' | 'danger' | 'ok';
}): JSX.Element {
  const percent = Math.max(0, Math.min(value, 100));
  const auto = percent > 90 ? 'danger' : percent > 75 ? 'warn' : tone;
  const colors: Record<string, string> = {
    accent: 'bg-uryx-accent',
    warn: 'bg-uryx-warn',
    danger: 'bg-uryx-danger',
    ok: 'bg-uryx-ok',
  };

  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <span className="text-xs text-slate-400">{label}</span>
        <span className="font-mono text-xs text-slate-300">
          {percent.toFixed(0)}%{detail ? ` · ${detail}` : ''}
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-black/40">
        <div
          className={cn('h-full rounded-full transition-all duration-500', colors[auto])}
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}

/** Boş durum kutusu. */
export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}): JSX.Element {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-16 text-center">
      {icon && <div className="text-slate-600">{icon}</div>}
      <div>
        <p className="text-sm font-medium text-slate-300">{title}</p>
        {description && (
          <p className="mx-auto mt-1 max-w-md text-[13px] leading-relaxed text-slate-500">
            {description}
          </p>
        )}
      </div>
      {action}
    </div>
  );
}

/** Yükleniyor göstergesi. */
export function Loading({ label }: { label?: string }): JSX.Element {
  const { t } = useI18n();
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-sm text-slate-500">
      <Loader2 size={16} className="animate-spin" />
      {label ?? t('common.loading')}
    </div>
  );
}

/** Hata kutusu. */
export function ErrorBox({ message, action }: { message: string; action?: ReactNode }): JSX.Element {
  return (
    <div className="m-6 rounded-lg border border-uryx-danger/40 bg-uryx-danger/10 p-4">
      <p className="text-sm text-rose-200">{message}</p>
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

/** Anahtar/değer satırı. */
export function InfoRow({ label, value }: { label: string; value: ReactNode }): JSX.Element {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1.5">
      <span className="text-xs text-slate-500">{label}</span>
      <span className="min-w-0 truncate text-right text-xs text-slate-300">{value}</span>
    </div>
  );
}

/** Açma/kapama anahtarı. */
export function Toggle({
  checked,
  onChange,
  label,
  description,
  disabled,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
  description?: string;
  disabled?: boolean;
}): JSX.Element {
  const { t } = useI18n();
  const control = (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label || t('common.toggle')}
      disabled={disabled}
      onClick={() => !disabled && onChange(!checked)}
      className={cn(
        'relative h-5 w-9 shrink-0 cursor-pointer rounded-full border-0 p-0 transition-colors',
        checked ? 'bg-uryx-accent' : 'bg-slate-700',
        disabled && 'cursor-not-allowed',
      )}
    >
      <span
        aria-hidden
        className={cn(
          'absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-transform duration-200',
          checked ? 'translate-x-4' : 'translate-x-0',
        )}
      />
    </button>
  );

  if (!label) return control;

  return (
    <label
      className={cn(
        'flex cursor-pointer items-start justify-between gap-4 py-2',
        disabled && 'cursor-not-allowed opacity-50',
      )}
    >
      <span className="min-w-0">
        <span className="block text-sm text-slate-200">{label}</span>
        {description && (
          <span className="mt-0.5 block min-w-0 text-xs leading-relaxed text-slate-500 [overflow-wrap:anywhere]">
            {description}
          </span>
        )}
      </span>
      <span className="mt-0.5 shrink-0">{control}</span>
    </label>
  );
}
