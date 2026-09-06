/** Sağ altta beliren bildirim yığını. */

import { AlertTriangle, CheckCircle2, Info, X, XCircle } from 'lucide-react';

import { cn } from '@/lib/cn';
import { useI18n } from '@/lib/i18n';
import { useUIStore, type Toast } from '@/stores/uiStore';

const ICONS = {
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  error: XCircle,
} as const;

const STYLES: Record<Toast['kind'], string> = {
  info: 'border-uryx-border bg-uryx-panel text-slate-200',
  success: 'border-uryx-ok/40 bg-uryx-ok/10 text-emerald-200',
  warning: 'border-uryx-warn/40 bg-uryx-warn/10 text-amber-200',
  error: 'border-uryx-danger/40 bg-uryx-danger/10 text-rose-200',
};

export function ToastStack(): JSX.Element | null {
  const { t } = useI18n();
  const { toasts, dismissToast } = useUIStore();
  if (!toasts.length) return null;

  return (
    <div className="pointer-events-none fixed bottom-6 right-6 z-[80] flex w-[22rem] max-w-[calc(100vw-2rem)] flex-col gap-2">
      {toasts.map((toast) => {
        const Icon = ICONS[toast.kind];
        return (
          <div
            key={toast.id}
            role="status"
            className={cn(
              'pointer-events-auto flex animate-slide-up items-start gap-2.5 rounded-lg border p-3 shadow-lg backdrop-blur',
              STYLES[toast.kind],
            )}
          >
            <Icon size={17} className="mt-0.5 shrink-0" />
            <p className="flex-1 text-sm leading-snug">{toast.message}</p>
            <button
              type="button"
              onClick={() => dismissToast(toast.id)}
              className="shrink-0 rounded p-0.5 opacity-60 transition-opacity hover:opacity-100"
              aria-label={t('toast.dismiss')}
            >
              <X size={14} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
