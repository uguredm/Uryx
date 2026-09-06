/** Uygulama güncellemesini Uryx arayüzü içinde yöneten modal. */

import { useEffect, useState } from 'react';
import { AlertTriangle, Download, RefreshCw, X } from 'lucide-react';
import type { UpdateState } from '@shared/ipc';

import { useI18n } from '@/lib/i18n';

const IDLE: UpdateState = { phase: 'idle', version: null, percent: 0, message: null };

export function UpdateModal(): JSX.Element | null {
  const { t } = useI18n();
  const [update, setUpdate] = useState<UpdateState>(IDLE);

  useEffect(() => {
    const bridge = window.uryx;
    if (!bridge) return;
    void bridge.updater.getState().then(setUpdate);
    return bridge.on('updater:state', (payload) => setUpdate(payload as UpdateState));
  }, []);

  if (update.phase === 'idle') return null;

  const working =
    update.phase === 'checking' ||
    update.phase === 'downloading' ||
    update.phase === 'ready';
  const title =
    update.phase === 'checking'
      ? t('update.checking')
      : update.phase === 'available'
        ? t('update.available')
        : update.phase === 'downloading'
          ? t('update.downloading')
          : update.phase === 'ready'
            ? t('update.ready')
            : t('update.failed');

  const respond = async (action: 'install' | 'later'): Promise<void> => {
    const next = await window.uryx?.updater.respond(action);
    if (next) setUpdate(next);
  };

  const retry = async (): Promise<void> => {
    const next = await window.uryx?.updater.check();
    if (next) setUpdate(next);
  };

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 p-6 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="update-title"
    >
      <div className="w-full max-w-md animate-slide-up overflow-hidden rounded-lg border border-uryx-border bg-uryx-surface shadow-2xl">
        <div className="flex items-start gap-3 border-b border-uryx-border bg-uryx-accent/5 p-5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-uryx-accent/15 text-uryx-accent">
            {update.phase === 'error' ? (
              <AlertTriangle size={20} className="text-uryx-warn" />
            ) : working ? (
              <RefreshCw size={20} className="animate-spin" />
            ) : (
              <Download size={20} />
            )}
          </div>
          <div className="min-w-0 flex-1">
            <h2 id="update-title" className="text-base font-semibold text-slate-100">
              {title}
            </h2>
            <p className="mt-1 text-[13px] leading-relaxed text-slate-400">{update.message}</p>
          </div>
          {!working && (
            <button
              type="button"
              onClick={() => void respond('later')}
              className="rounded p-1 text-slate-500 transition-colors hover:bg-white/5 hover:text-slate-300"
              aria-label={t('update.later')}
            >
              <X size={16} />
            </button>
          )}
        </div>

        {update.phase === 'downloading' && (
          <div className="space-y-2 px-5 py-4">
            <div className="flex justify-between text-[12px] text-slate-400">
              <span>{t('update.progress')}</span>
              <span>{Math.round(update.percent)}%</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-slate-800">
              <div
                className="h-full rounded-full bg-uryx-accent transition-[width] duration-300"
                style={{ width: `${update.percent}%` }}
              />
            </div>
          </div>
        )}

        {!working && (
          <div className="flex justify-end gap-2 border-t border-uryx-border bg-uryx-panel/50 p-4">
            <button type="button" className="btn-outline" onClick={() => void respond('later')}>
              {t('update.later')}
            </button>
            {update.phase === 'error' && (
              <button
                type="button"
                className="btn bg-uryx-accent text-slate-950 hover:brightness-110"
                onClick={() => void retry()}
              >
                <RefreshCw size={15} />
                {t('update.retry')}
              </button>
            )}
            {update.phase === 'available' && (
              <button
                type="button"
                className="btn bg-uryx-accent text-slate-950 hover:brightness-110"
                onClick={() => void respond('install')}
                autoFocus
              >
                <Download size={15} />
                {t('update.install')}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
