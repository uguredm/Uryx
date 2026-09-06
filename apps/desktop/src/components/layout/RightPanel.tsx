/** Sağ panel: aktif model, kaynak kullanımı, kullanılan bağlam ve servisler. */

import { Cpu, FileText, HardDrive, MemoryStick, Server, Sparkles, Wrench, Zap } from 'lucide-react';

import { InfoRow, MetricBar, StatusBadge } from '@/components/common/Primitives';
import { useSystemStore } from '@/hooks/useSystemStatus';
import { toolCardLabel, toolDisplayStatus } from '@/lib/confirmResponse';
import { formatPercent, mbToGb, serviceStateLabel, truncate } from '@/lib/format';
import { dateLocale, useI18n } from '@/lib/i18n';
import { serviceDisplayName, toolDisplayName } from '@/lib/apiText';
import { useChatStore } from '@/stores/chatStore';
import { useSettingsStore } from '@/stores/settingsStore';

export function RightPanel(): JSX.Element {
  const { t, language } = useI18n();
  const status = useSystemStore((state) => state.status);
  const settings = useSettingsStore((state) => state.settings);
  const { activeSources, activeMemories, liveToolCalls } = useChatStore();

  const metrics = status?.metrics;
  const gpu = metrics?.gpu;
  const tempValue =
    language === 'tr'
      ? settings.temperature.toFixed(2).replace('.', ',')
      : settings.temperature.toFixed(2);

  return (
    <aside className="flex w-72 shrink-0 flex-col border-l border-uryx-border bg-uryx-surface">
      <div className="scroll-area flex-1 space-y-5 p-4">
        <section>
          <SectionTitle icon={<Zap size={13} />} title={t('panel.model')} />
          <div className="card p-3">
            <p className="truncate text-[13px] font-medium text-slate-200">
              {status?.model.model_id ?? settings.modelName}
            </p>
            <div className="mt-1.5">
              <StatusBadge
                state={status?.model.loaded ? 'up' : 'down'}
                label={status?.model.loaded ? t('panel.loaded') : t('panel.notLoaded')}
              />
            </div>
            <div className="mt-2 border-t border-uryx-border pt-2">
              <InfoRow
                label={t('panel.context')}
                value={`${(status?.model.max_model_len ?? settings.contextLength).toLocaleString(dateLocale(language))} token`}
              />
              <InfoRow label={t('panel.temp')} value={tempValue} />
            </div>
          </div>
        </section>

        <section>
          <SectionTitle icon={<Cpu size={13} />} title={t('panel.resources')} />
          <div className="card space-y-3 p-3">
            {metrics ? (
              <>
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
                {gpu?.available ? (
                  <>
                    <MetricBar
                      label="VRAM"
                      value={gpu.vram_percent}
                      detail={`${mbToGb(gpu.vram_used_mb, language)} / ${mbToGb(gpu.vram_total_mb, language)}`}
                    />
                    <MetricBar label="GPU" value={gpu.utilization_percent} />
                    <p className="truncate pt-0.5 text-[11px] text-slate-600" title={gpu.name}>
                      {gpu.name}
                      {gpu.temperature_c ? ` · ${gpu.temperature_c}°C` : ''}
                    </p>
                  </>
                ) : (
                  <p className="text-[11.5px] leading-relaxed text-slate-600">
                    {t('panel.gpuUnread')}
                  </p>
                )}
                {metrics.disks.slice(0, 2).map((disk) => (
                  <MetricBar
                    key={disk.mount}
                    label={`Disk ${disk.mount}`}
                    value={disk.percent}
                    detail={`${disk.used_gb.toFixed(0)} / ${disk.total_gb.toFixed(0)} GB`}
                  />
                ))}
                {metrics.source === 'container' && (
                  <p className="text-[11px] text-uryx-warn">{t('panel.containerMetrics')}</p>
                )}
              </>
            ) : (
              <p className="text-[12px] text-slate-500">{t('panel.metricsWait')}</p>
            )}
          </div>
        </section>

        {activeMemories.length > 0 && (
          <section>
            <SectionTitle
              icon={<Sparkles size={13} />}
              title={t('panel.usedMemory')}
              count={activeMemories.length}
            />
            <div className="space-y-1.5">
              {activeMemories.map((memory) => (
                <div key={memory.id} className="card p-2.5">
                  <p className="text-[12px] leading-relaxed text-slate-300">
                    {truncate(memory.content, 130)}
                  </p>
                  <p className="mt-1 font-mono text-[10.5px] text-slate-600">
                    {memory.category} · {(memory.score * 100).toFixed(0)}%
                  </p>
                </div>
              ))}
            </div>
          </section>
        )}

        {activeSources.length > 0 && (
          <section>
            <SectionTitle
              icon={<FileText size={13} />}
              title={t('panel.usedDocs')}
              count={activeSources.length}
            />
            <div className="space-y-1.5">
              {activeSources.map((source, index) => (
                <div key={source.chunk_id} className="card p-2.5">
                  <p className="flex items-baseline gap-1.5 text-[12px] font-medium text-slate-200">
                    <span className="font-mono text-uryx-accent">[{index + 1}]</span>
                    <span className="min-w-0 truncate">{source.filename}</span>
                  </p>
                  <p className="mt-0.5 font-mono text-[10.5px] text-slate-600">
                    {source.page ? `${t('panel.page', { page: source.page })} · ` : ''}
                    {t('panel.match', { pct: (source.score * 100).toFixed(0) })}
                  </p>
                </div>
              ))}
            </div>
          </section>
        )}

        {liveToolCalls.length > 0 && (
          <section>
            <SectionTitle
              icon={<Wrench size={13} />}
              title={t('panel.tools')}
              count={liveToolCalls.length}
            />
            <div className="space-y-1.5">
              {liveToolCalls.map((call) => {
                const display = toolDisplayStatus(call.toolName, call.status, call.result);
                return (
                  <div key={call.callId} className="card flex items-center gap-2 p-2.5">
                    <span className="min-w-0 flex-1 truncate text-[12px] text-slate-300">
                      {toolCardLabel(
                        call.toolName,
                        toolDisplayName(call.toolName, call.displayName, language),
                        call.arguments,
                        call.result,
                      )}
                    </span>
                    <StatusBadge
                      state={
                        display === 'success'
                          ? 'up'
                          : display === 'running'
                            ? 'starting'
                            : display === 'rejected'
                              ? 'degraded'
                              : 'down'
                      }
                      label={
                        display === 'success'
                          ? t('tool.done')
                          : display === 'running'
                            ? t('tool.status.running')
                            : display === 'rejected'
                              ? t('tool.rejected')
                              : t('tool.error')
                      }
                    />
                  </div>
                );
              })}
            </div>
          </section>
        )}

        <section>
          <SectionTitle icon={<Server size={13} />} title={t('panel.services')} />
          <div className="card divide-y divide-uryx-border">
            {(status?.services ?? []).map((service) => (
              <div key={service.name} className="flex items-center justify-between gap-2 px-3 py-2">
                <span className="min-w-0 truncate text-[12px] text-slate-300">
                  {serviceDisplayName(service.name, service.display_name, language)}
                </span>
                <StatusBadge
                  state={service.state}
                  label={serviceStateLabel(service.state, language)}
                />
              </div>
            ))}
            {!status && (
              <p className="px-3 py-2 text-[12px] text-slate-500">{t('panel.checking')}</p>
            )}
          </div>
        </section>
      </div>

      <div className="border-t border-uryx-border px-4 py-2.5">
        <div className="flex items-center justify-between text-[11px] text-slate-600">
          <span className="flex items-center gap-1.5">
            <MemoryStick size={11} />
            {metrics ? formatPercent(metrics.ram_percent, language) : '—'}
          </span>
          <span className="flex items-center gap-1.5">
            <HardDrive size={11} />
            {status?.host_bridge_connected ? t('tray.bridgeUp') : t('panel.bridgeMissing')}
          </span>
        </div>
      </div>
    </aside>
  );
}

function SectionTitle({
  icon,
  title,
  count,
}: {
  icon: JSX.Element;
  title: string;
  count?: number;
}): JSX.Element {
  return (
    <h2 className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
      {icon}
      {title}
      {count !== undefined && (
        <span className="ml-auto rounded-full bg-white/5 px-1.5 py-0.5 text-[10px] font-normal">
          {count}
        </span>
      )}
    </h2>
  );
}
