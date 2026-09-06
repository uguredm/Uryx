/**
 * Riskli araç onayı — Claude / Continue: geri sayım, klavye, oturum izni.
 * Karar backend'de doğrulanır; modal yalnızca arayüzdür.
 */

import { useEffect, useState } from 'react';
import { AlertTriangle, ShieldAlert, X } from 'lucide-react';

import { cn } from '@/lib/cn';
import {
  canRememberConfirm,
  confirmArgumentEntries,
  mcpConfirmImpact,
  sealDigest,
  toolCardLabel,
} from '@/lib/confirmResponse';
import { riskLabel } from '@/lib/format';
import { useI18n } from '@/lib/i18n';
import { localizeApiText, toolDisplayName } from '@/lib/apiText';
import { useChatStore } from '@/stores/chatStore';

/** API `CONFIRMATION_TIMEOUT` ile aynı (120s). */
export const TOOL_CONFIRM_TIMEOUT_MS = 120_000;

export function remainingConfirmMs(startedAt: number, now = Date.now()): number {
  return Math.max(0, TOOL_CONFIRM_TIMEOUT_MS - (now - startedAt));
}

export function ToolConfirmModal(): JSX.Element | null {
  const { t, language } = useI18n();
  const pending = useChatStore((state) => state.pendingConfirmation);
  const respond = useChatStore((state) => state.respondConfirmation);
  const [allowSession, setAllowSession] = useState(false);
  const [startedAt, setStartedAt] = useState(0);
  const [remainingMs, setRemainingMs] = useState(TOOL_CONFIRM_TIMEOUT_MS);

  useEffect(() => {
    if (!pending) {
      setAllowSession(false);
      return;
    }
    const start = Date.now();
    setStartedAt(start);
    setRemainingMs(TOOL_CONFIRM_TIMEOUT_MS);
    const tick = window.setInterval(() => {
      const left = remainingConfirmMs(start);
      setRemainingMs(left);
      if (left <= 0) {
        window.clearInterval(tick);
        respond(false);
      }
    }, 250);
    return () => window.clearInterval(tick);
  }, [pending, respond]);

  useEffect(() => {
    if (!pending) return;
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === 'Escape' || event.key === 'n' || event.key === 'N') {
        event.preventDefault();
        respond(false);
        return;
      }
      if (event.key === 'Enter' || event.key === 'y' || event.key === 'Y') {
        event.preventDefault();
        respond(true, allowSession);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [pending, respond, allowSession]);

  if (!pending) return null;

  const high = pending.risk_level === 'high';
  const entries = confirmArgumentEntries(pending);
  const progress = startedAt === 0 ? 1 : remainingMs / TOOL_CONFIRM_TIMEOUT_MS;
  const seconds = Math.ceil(remainingMs / 1000);

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/70 p-6 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="tool-confirm-title"
    >
      <div className="w-full max-w-lg animate-slide-up overflow-hidden rounded-xl border border-uryx-border bg-uryx-surface shadow-2xl">
        <div
          className={cn(
            'flex items-start gap-3 border-b border-uryx-border p-5',
            high ? 'bg-uryx-danger/10' : 'bg-uryx-warn/10',
          )}
        >
          <div
            className={cn(
              'flex h-10 w-10 shrink-0 items-center justify-center rounded-lg',
              high ? 'bg-uryx-danger/20 text-uryx-danger' : 'bg-uryx-warn/20 text-uryx-warn',
            )}
          >
            {high ? <ShieldAlert size={20} /> : <AlertTriangle size={20} />}
          </div>
          <div className="min-w-0 flex-1">
            <h2 id="tool-confirm-title" className="text-base font-semibold text-slate-100">
              {t('confirm.title')}
            </h2>
            <p className="mt-0.5 text-[13px] text-slate-400">
              {t('confirm.body')}
            </p>
          </div>
          <button
            type="button"
            onClick={() => respond(false)}
            className="rounded p-1 text-slate-500 transition-colors hover:bg-white/5 hover:text-slate-300"
            aria-label={t('confirm.close')}
          >
            <X size={16} />
          </button>
        </div>

        <div className="h-1 bg-uryx-bg" aria-hidden>
          <div
            className={cn('h-full transition-[width] duration-200', high ? 'bg-uryx-danger' : 'bg-uryx-accent')}
            style={{ width: `${Math.round(progress * 100)}%` }}
          />
        </div>

        <div className="space-y-4 p-5">
          <div>
            <p className="label">{t('confirm.tool')}</p>
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-slate-100">
                {toolCardLabel(
                  pending.tool_name,
                  toolDisplayName(pending.tool_name, pending.display_name, language),
                  pending.arguments,
                )}
              </span>
              <span
                className={cn(
                  'badge',
                  high
                    ? 'bg-uryx-danger/15 text-uryx-danger'
                    : 'bg-uryx-warn/15 text-uryx-warn',
                )}
              >
                {riskLabel(pending.risk_level, language)}
              </span>
            </div>
            <p className="mt-1 font-mono text-[11px] text-slate-500">{pending.tool_name}</p>
            {sealDigest(pending.fingerprint) && (
              <p className="mt-1 font-mono text-[11px] text-slate-500">
                {t('confirm.seal', { id: sealDigest(pending.fingerprint) ?? '' })}
              </p>
            )}
          </div>

          <div>
            <p className="label">{t('confirm.params')}</p>
            {entries.length === 0 ? (
              <p className="text-[13px] text-slate-500">{t('confirm.noParams')}</p>
            ) : (
              <div className="max-h-48 space-y-1.5 overflow-y-auto rounded-lg border border-uryx-border bg-uryx-bg p-3">
                {entries.map(([key, value]) => (
                  <div key={key} className="flex gap-2 text-[13px]">
                    <span className="shrink-0 font-mono text-slate-500">{key}:</span>
                    <span className="min-w-0 flex-1 break-all font-mono text-slate-200">
                      {typeof value === 'string' ? value : JSON.stringify(value)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div>
            <p className="label">{t('confirm.impact')}</p>
            <p className="text-[13px] leading-relaxed text-slate-300">
              {localizeApiText(mcpConfirmImpact(pending), language) || t('confirm.impactDefault')}
            </p>
          </div>

          {canRememberConfirm(pending) && (
            <label className="flex items-start gap-2 text-[13px] text-slate-300">
              <input
                type="checkbox"
                className="mt-0.5 accent-uryx-accent"
                checked={allowSession}
                onChange={(event) => setAllowSession(event.target.checked)}
              />
              <span>{t('confirm.remember')}</span>
            </label>
          )}
        </div>

        <div className="flex items-center justify-between gap-2 border-t border-uryx-border bg-uryx-panel/50 p-4">
          <p className="text-[11.5px] text-slate-500">
            {t('confirm.timer', { n: seconds })}
          </p>
          <div className="flex gap-2">
            <button type="button" className="btn-outline" onClick={() => respond(false)}>
              {t('confirm.deny')}
            </button>
            <button
              type="button"
              className={cn(
                'btn',
                high
                  ? 'bg-uryx-danger text-slate-950 hover:bg-rose-400'
                  : 'bg-uryx-accent text-slate-950 hover:brightness-110',
              )}
              onClick={() => respond(true, allowSession)}
              autoFocus
            >
              {t('confirm.allow')}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
