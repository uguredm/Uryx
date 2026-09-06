/** Sistem durumu ekranı: servisler, metrikler, Docker kontrolü, loglar. */

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  AlertTriangle,
  Cpu,
  HardDrive,
  Loader2,
  Play,
  RefreshCw,
  RotateCw,
  Square,
  Stethoscope,
  Terminal,
} from 'lucide-react';

import { InfoRow, MetricBar, StatusBadge, ViewHeader } from '@/components/common/Primitives';
import { useSystemStore } from '@/hooks/useSystemStatus';
import { api } from '@/lib/api';
import { formatDateTime, mbToGb, serviceStateLabel } from '@/lib/format';
import { useI18n } from '@/lib/i18n';
import { localizeApiText, serviceDisplayName } from '@/lib/apiText';
import { useUIStore } from '@/stores/uiStore';

type Action = 'start' | 'stop' | 'restart' | 'diagnose' | 'docker' | null;

export function SystemView(): JSX.Element {
  const { t, language } = useI18n();
  const [busy, setBusy] = useState<Action>(null);
  const [logs, setLogs] = useState<string>('');
  const [logService, setLogService] = useState('');

  const status = useSystemStore((state) => state.status);
  const connected = useSystemStore((state) => state.connected);
  const lastUpdate = useSystemStore((state) => state.lastUpdate);
  const composeProgress = useSystemStore((state) => state.composeProgress);
  const pushToast = useUIStore((state) => state.pushToast);

  const services = useQuery({
    queryKey: ['docker-services'],
    queryFn: async () => window.uryx?.services.status() ?? null,
    refetchInterval: 10_000,
    enabled: Boolean(window.uryx),
  });
  const effectiveConfig = useQuery({
    queryKey: ['system-config'],
    queryFn: () => api.system.config(),
    retry: 0,
  });
  const rawLlmConfig = effectiveConfig.data?.llm;
  const llmConfig =
    rawLlmConfig && typeof rawLlmConfig === 'object'
      ? (rawLlmConfig as Record<string, unknown>)
      : {};

  /** Docker compose eylemi çalıştırır. */
  const runAction = async (action: Exclude<Action, null>): Promise<void> => {
    const bridge = window.uryx;
    if (!bridge) {
      pushToast('warning', t('system.desktopOnly'));
      return;
    }
    setBusy(action);
    try {
      if (action === 'diagnose') {
        const snapshot = await bridge.services.diagnose();
        void services.refetch();
        const hint = snapshot.hints?.[0];
        pushToast(
          snapshot.apiReachable ? 'success' : 'warning',
          hint ??
            (snapshot.apiReachable
              ? t('system.apiOk')
              : t('system.apiWait')),
        );
        return;
      }
      if (action === 'docker') {
        const result = await bridge.services.openDocker();
        pushToast(result.ok ? 'success' : 'error', result.message);
        void services.refetch();
        return;
      }
      const result =
        action === 'start'
          ? await bridge.services.start()
          : action === 'stop'
            ? await bridge.services.stop()
            : await bridge.services.restart();
      pushToast(result.ok ? 'success' : 'error', result.message);
      if (!result.ok && result.output) setLogs(result.output);
      void services.refetch();
    } catch (error) {
      pushToast('error', error instanceof Error ? error.message : t('system.actionFail'));
    } finally {
      setBusy(null);
    }
  };

  /** Servis loglarını çeker. */
  const loadLogs = async (): Promise<void> => {
    const bridge = window.uryx;
    if (!bridge) return;
    try {
      setLogs(await bridge.services.logs(logService, 300));
    } catch (error) {
      pushToast('error', error instanceof Error ? error.message : t('system.logsFail'));
    }
  };

  const metrics = status?.metrics;
  const gpu = metrics?.gpu;
  const dockerInfo = services.data;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <ViewHeader
        title={t('view.system')}
        description={
          connected
            ? t('system.live', {
                time: lastUpdate ? formatDateTime(new Date(lastUpdate).toISOString(), language) : '—',
              })
            : t('system.poll')
        }
        actions={
          <>
            <button
              type="button"
              className="btn-outline"
              onClick={() => void runAction('start')}
              disabled={busy !== null}
            >
              {busy === 'start' ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Play size={14} />
              )}
              {t('system.start')}
            </button>
            <button
              type="button"
              className="btn-outline"
              onClick={() => void runAction('restart')}
              disabled={busy !== null}
            >
              {busy === 'restart' ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <RotateCw size={14} />
              )}
              {t('system.restart')}
            </button>
            <button
              type="button"
              className="btn-outline"
              onClick={() => void runAction('diagnose')}
              disabled={busy !== null}
            >
              {busy === 'diagnose' ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Stethoscope size={14} />
              )}
              {t('system.diagnose')}
            </button>
            <button
              type="button"
              className="btn-danger"
              onClick={() => void runAction('stop')}
              disabled={busy !== null}
            >
              {busy === 'stop' ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Square size={14} />
              )}
              {t('system.stop')}
            </button>
          </>
        }
      />

      <div className="scroll-area flex-1 space-y-5 p-6">
        {composeProgress && (
          <Banner
            tone={composeProgress.phase === 'error' ? 'danger' : 'warn'}
            message={
              composeProgress.phase
                ? `${composeProgress.phase} · ${composeProgress.message}`
                : composeProgress.message
            }
          />
        )}
        {/* Ortam uyarıları */}
        {dockerInfo && !dockerInfo.dockerAvailable && (
          <Banner
            tone="danger"
            message={
              dockerInfo.error ?? t('system.dockerDown')
            }
            action={
              <button
                type="button"
                className="btn-outline h-8 py-1 text-xs"
                onClick={() => void runAction('docker')}
                disabled={busy !== null}
              >
                {busy === 'docker' ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : null}
                {dockerInfo.dockerDesktopInstalled === false
                  ? t('system.dockerInstall')
                  : t('system.dockerOpen')}
              </button>
            }
          />
        )}
        {dockerInfo?.dockerAvailable && dockerInfo.apiReachable === false && (
          <Banner
            tone="warn"
            message={
              dockerInfo.apiLatencyMs == null
                ? t('system.apiHostWait')
                : t('system.apiHealthFail')
            }
          />
        )}
        {dockerInfo?.hints?.map((hint) => (
          <Banner key={hint} tone="warn" message={hint} />
        ))}
        {dockerInfo?.dockerAvailable && !dockerInfo.gpuAvailable && (
          <Banner
            tone="warn"
            message={t('system.gpuMissing')}
          />
        )}
        {status?.last_error && (
          <Banner tone="warn" message={t('system.lastError', { error: status.last_error })} />
        )}

        {/* Servisler */}
        <section className="mx-auto max-w-4xl">
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            {t('panel.services')}
          </h2>
          <div className="card divide-y divide-uryx-border">
            {(status?.services ?? []).map((service) => (
              <div key={service.name} className="flex items-center gap-3 px-4 py-3">
                <div className="min-w-0 flex-1">
                  <p className="text-[13.5px] text-slate-200">
                    {serviceDisplayName(service.name, service.display_name, language)}
                  </p>
                  {localizeApiText(service.detail, language) && (
                    <p className="mt-0.5 text-[11.5px] text-slate-500">
                      {localizeApiText(service.detail, language)}
                    </p>
                  )}
                  {service.url && (
                    <p className="mt-0.5 font-mono text-[11px] text-slate-600">{service.url}</p>
                  )}
                </div>
                {service.latency_ms !== null && (
                  <span className="shrink-0 font-mono text-[11px] text-slate-600">
                    {service.latency_ms} ms
                  </span>
                )}
                {service.container_status && (
                  <span className="shrink-0 font-mono text-[11px] text-slate-600">
                    {service.container_status}
                  </span>
                )}
                <StatusBadge state={service.state} label={serviceStateLabel(service.state, language)} />
              </div>
            ))}
            {!status && (
              <p className="px-4 py-3 text-[13px] text-slate-500">{t('system.checking')}</p>
            )}
          </div>
          {dockerInfo?.apiReachable === false && dockerInfo.dockerAvailable && (
            <p className="mt-2 text-[12px] text-slate-500">
              {dockerInfo.apiLatencyMs != null
                ? t('system.healthPoll', { ms: dockerInfo.apiLatencyMs })
                : t('system.healthPollNoMs')}
            </p>
          )}
        </section>

        {dockerInfo && dockerInfo.services.length > 0 && (
          <section className="mx-auto max-w-4xl">
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
              {t('system.composeHost')}
              {dockerInfo.engineState
                ? ` · ${
                    dockerInfo.engineState === 'up'
                      ? t('system.engine.up')
                      : dockerInfo.engineState === 'starting'
                        ? t('system.engine.starting')
                        : dockerInfo.engineState === 'down'
                          ? t('system.engine.down')
                          : t('system.engine', { state: dockerInfo.engineState })
                  }`
                : ''}
            </h2>
            <div className="card divide-y divide-uryx-border">
              {dockerInfo.services.map((service) => (
                <div key={service.name} className="flex items-center gap-3 px-4 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-[13.5px] text-slate-200">{service.name}</p>
                    <p className="mt-0.5 font-mono text-[11px] text-slate-600">
                      {service.state}
                      {service.health ? ` · ${service.health}` : ''}
                    </p>
                  </div>
                  <button
                    type="button"
                    className="btn-outline h-8 py-1 text-xs"
                    onClick={() => {
                      setLogService(service.name);
                      const bridge = window.uryx;
                      if (!bridge) return;
                      void bridge.services
                        .logs(service.name, 300)
                        .then((text) => setLogs(text))
                        .catch((error: unknown) => {
                          pushToast(
                            'error',
                            error instanceof Error ? error.message : t('system.logsFail'),
                          );
                        });
                    }}
                  >
                    <Terminal size={12} />
                    Log
                  </button>
                  <button
                    type="button"
                    className="btn-outline h-8 py-1 text-xs"
                    disabled={busy !== null}
                    onClick={() => {
                      const bridge = window.uryx;
                      if (!bridge) return;
                      setBusy('restart');
                      void bridge.services
                        .restart(service.name)
                        .then((result) => {
                          pushToast(result.ok ? 'success' : 'error', result.message);
                          void services.refetch();
                        })
                        .catch((error: unknown) => {
                          pushToast(
                            'error',
                            error instanceof Error ? error.message : t('system.restartFail'),
                          );
                        })
                        .finally(() => setBusy(null));
                    }}
                  >
                    <RotateCw size={12} />
                    {t('system.restart')}
                  </button>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Metrikler */}
        <div className="mx-auto grid max-w-4xl gap-4 md:grid-cols-2">
          <section className="card p-4">
            <h2 className="mb-3 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
              <Cpu size={13} />
              {t('system.cpuMem')}
            </h2>
            {metrics ? (
              <div className="space-y-3">
                <MetricBar
                  label="CPU"
                  value={metrics.cpu_percent}
                  detail={t('panel.cores', { n: metrics.cpu_cores })}
                />
                <MetricBar
                  label="RAM"
                  value={metrics.ram_percent}
                  detail={`${mbToGb(metrics.ram_used_mb, language)} / ${mbToGb(metrics.ram_total_mb, language)}`}
                />
                <div className="border-t border-uryx-border pt-2">
                  <InfoRow
                    label={t('system.source')}
                    value={
                      metrics.source === 'host' ? t('system.sourceHost') : t('system.sourceContainer')
                    }
                  />
                </div>
              </div>
            ) : (
              <p className="text-[13px] text-slate-500">{t('system.waiting')}</p>
            )}
          </section>

          <section className="card p-4">
            <h2 className="mb-3 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
              <HardDrive size={13} />
              {t('system.gpu')}
            </h2>
            {gpu?.available ? (
              <div className="space-y-3">
                <p className="truncate text-[13px] text-slate-200">{gpu.name}</p>
                <MetricBar
                  label="VRAM"
                  value={gpu.vram_percent}
                  detail={`${mbToGb(gpu.vram_used_mb, language)} / ${mbToGb(gpu.vram_total_mb, language)}`}
                />
                <MetricBar label={t('system.gpuUsage')} value={gpu.utilization_percent} />
                <div className="border-t border-uryx-border pt-2">
                  {gpu.temperature_c !== null && (
                    <InfoRow label={t('system.gpuTemp')} value={`${gpu.temperature_c}°C`} />
                  )}
                  {gpu.driver_version && (
                    <InfoRow label={t('system.gpuDriver')} value={gpu.driver_version} />
                  )}
                </div>
              </div>
            ) : (
              <p className="text-[13px] leading-relaxed text-slate-500">
                {t('system.gpuUnread')}
              </p>
            )}
          </section>
        </div>

        {/* Disk */}
        {metrics && metrics.disks.length > 0 && (
          <section className="mx-auto max-w-4xl card p-4">
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">
              {t('system.disks')}
            </h2>
            <div className="grid gap-3 sm:grid-cols-2">
              {metrics.disks.map((disk) => (
                <MetricBar
                  key={disk.mount}
                  label={disk.mount}
                  value={disk.percent}
                  detail={`${disk.used_gb.toFixed(0)} / ${disk.total_gb.toFixed(0)} GB`}
                />
              ))}
            </div>
          </section>
        )}

        {/* Model */}
        <section className="mx-auto max-w-4xl card p-4">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">
            {t('system.model')}
          </h2>
          <InfoRow label={t('system.model')} value={status?.model.model_id ?? '—'} />
          <InfoRow
            label={t('system.routing')}
            value={
              llmConfig.cloud_configured === true
                ? t('system.routingHybrid', {
                    provider: String(llmConfig.cloud_provider ?? llmConfig.cloud_model ?? t('system.routingCloud')),
                  })
                : t('system.routingLocal')
            }
          />
          <InfoRow
            label={t('system.status')}
            value={
              <StatusBadge
                state={status?.model.loaded ? 'up' : 'down'}
                label={status?.model.loaded ? t('panel.loaded') : t('panel.notLoaded')}
              />
            }
          />
          <InfoRow
            label={t('system.contextLen')}
            value={status?.model.max_model_len?.toLocaleString(language === 'en' ? 'en-US' : 'tr-TR') ?? '—'}
          />
          {localizeApiText(status?.model.detail, language) && (
            <InfoRow label={t('system.detail')} value={localizeApiText(status?.model.detail, language)} />
          )}
        </section>

        {/* Loglar */}
        <section className="mx-auto max-w-4xl card p-4">
          <div className="mb-3 flex items-center gap-2">
            <h2 className="flex flex-1 items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
              <Terminal size={13} />
              {t('system.logs')}
            </h2>
            <select
              value={logService}
              onChange={(event) => setLogService(event.target.value)}
              className="input h-8 w-44 py-1 text-xs"
            >
              <option value="">{t('system.allServices')}</option>
              <option value="uryx-api">uryx-api</option>
              <option value="llm">llm</option>
              <option value="whisper">whisper</option>
              <option value="tts">tts</option>
              <option value="qdrant">qdrant</option>
              <option value="postgres">postgres</option>
              <option value="docker-desktop">docker-desktop</option>
            </select>
            <button
              type="button"
              className="btn-outline h-8 py-1 text-xs"
              onClick={() => void loadLogs()}
            >
              <RefreshCw size={12} />
              {t('system.fetchLogs')}
            </button>
          </div>
          <pre className="max-h-80 overflow-auto rounded-lg border border-uryx-border bg-black/40 p-3 font-mono text-[11.5px] leading-relaxed text-slate-400">
            {logs || t('system.logsPlaceholder')}
          </pre>
        </section>
      </div>
    </div>
  );
}

function Banner({
  tone,
  message,
  action,
}: {
  tone: 'warn' | 'danger';
  message: string;
  action?: JSX.Element;
}): JSX.Element {
  const styles =
    tone === 'danger'
      ? 'border-uryx-danger/40 bg-uryx-danger/10 text-rose-200'
      : 'border-uryx-warn/40 bg-uryx-warn/10 text-amber-200';

  return (
    <div className={`mx-auto flex max-w-4xl items-start gap-2.5 rounded-lg border p-3 ${styles}`}>
      <AlertTriangle size={16} className="mt-0.5 shrink-0" />
      <p className="min-w-0 flex-1 text-[12.5px] leading-relaxed">{message}</p>
      {action}
    </div>
  );
}
