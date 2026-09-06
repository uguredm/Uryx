/** Araç listesi ve son çalıştırma geçmişi. */

import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query';
import { Cloud, Monitor, ShieldAlert, ShieldCheck, Wrench } from 'lucide-react';
import type { ToolDefinition } from '@shared/api';

import { ErrorBox, Loading, StatusBadge, Toggle, ViewHeader } from '@/components/common/Primitives';
import { api } from '@/lib/api';
import { cn } from '@/lib/cn';
import { formatDuration, formatRelative, riskLabel } from '@/lib/format';
import { useI18n, type MessageKey } from '@/lib/i18n';
import { localizeApiText, toolDisplayName } from '@/lib/apiText';
import { useUIStore } from '@/stores/uiStore';

const CATEGORY_KEYS: Record<string, MessageKey> = {
  application: 'tools.cat.application',
  filesystem: 'tools.cat.filesystem',
  system: 'tools.cat.system',
  git: 'tools.cat.git',
  shell: 'tools.cat.shell',
  docker: 'tools.cat.docker',
  mcp: 'tools.cat.mcp',
  rag: 'tools.cat.rag',
  memory: 'tools.cat.memory',
  general: 'tools.cat.general',
  web: 'tools.cat.web',
};

export function ToolsView(): JSX.Element {
  const { t, language } = useI18n();
  const queryClient = useQueryClient();
  const pushToast = useUIStore((state) => state.pushToast);

  const tools = useQuery({ queryKey: ['tools'], queryFn: () => api.tools.list() });
  const history = useQuery({
    queryKey: ['tool-history'],
    queryFn: () => api.tools.history(),
    refetchInterval: 8000,
  });
  const hostAudit = useQuery({
    queryKey: ['host-audit'],
    queryFn: () => window.uryx?.host.status() ?? null,
    refetchInterval: 8000,
    enabled: Boolean(window.uryx),
  });

  const setEnabled = useMutation({
    mutationFn: ({ name, enabled }: { name: string; enabled: boolean }) =>
      api.tools.setEnabled(name, enabled),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['tools'] }),
    onError: (error) =>
      pushToast('error', error instanceof Error ? error.message : t('toast.toolsToggleFail')),
  });

  const grouped = (tools.data?.tools ?? []).reduce<Record<string, ToolDefinition[]>>(
    (accumulator, tool) => {
      (accumulator[tool.category] ??= []).push(tool);
      return accumulator;
    },
    {},
  );

  return (
    <div className="flex h-full min-h-0 flex-col">
      <ViewHeader
        title={t('view.tools')}
        description={t('view.tools.desc')}
        actions={
          tools.data && (
            <StatusBadge
              state={tools.data.host_bridge_connected ? 'up' : 'down'}
              label={
                tools.data.host_bridge_connected
                  ? t('tools.bridgeUp')
                  : t('tools.bridgeDown')
              }
            />
          )
        }
      />

      <div className="scroll-area flex-1 p-6">
        {tools.isLoading && <Loading label={t('tools.loading')} />}

        {tools.isError && (
          <ErrorBox
            message={tools.error instanceof Error ? tools.error.message : t('tools.loadFail')}
            action={
              <button type="button" className="btn-outline" onClick={() => void tools.refetch()}>
                {t('action.retry')}
              </button>
            }
          />
        )}

        <div className="mx-auto max-w-4xl space-y-6">
          {Object.entries(grouped).map(([category, entries]) => (
            <section key={category}>
              <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                {CATEGORY_KEYS[category] ? t(CATEGORY_KEYS[category]) : category}
              </h2>
              <div className="card divide-y divide-uryx-border">
                {entries.map((tool) => (
                  <div key={tool.name} className="p-3.5">
                    <div className="flex items-start gap-3">
                      <div
                        className={cn(
                          'mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg',
                          tool.risk === 'high'
                            ? 'bg-uryx-danger/15 text-uryx-danger'
                            : tool.risk === 'medium'
                              ? 'bg-uryx-warn/15 text-uryx-warn'
                              : 'bg-uryx-ok/15 text-uryx-ok',
                        )}
                      >
                        {tool.risk === 'low' ? <ShieldCheck size={15} /> : <ShieldAlert size={15} />}
                      </div>

                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-[13.5px] font-medium text-slate-200">
                            {toolDisplayName(tool.name, tool.display_name, language)}
                          </span>
                          <span
                            className={cn(
                              'badge',
                              tool.risk === 'high'
                                ? 'bg-uryx-danger/15 text-uryx-danger'
                                : tool.risk === 'medium'
                                  ? 'bg-uryx-warn/15 text-uryx-warn'
                                  : 'bg-uryx-ok/15 text-uryx-ok',
                            )}
                          >
                            {riskLabel(tool.risk, language)}
                          </span>
                          <span className="badge bg-white/5 text-slate-400">
                            {tool.execution === 'host' ? (
                              <>
                                <Monitor size={10} /> {t('tools.exec.host')}
                              </>
                            ) : (
                              <>
                                <Cloud size={10} /> {t('tools.exec.backend')}
                              </>
                            )}
                          </span>
                        </div>

                        {localizeApiText(tool.description, language) && (
                          <p className="mt-1 text-[12.5px] leading-relaxed text-slate-400">
                            {localizeApiText(tool.description, language)}
                          </p>
                        )}

                        {localizeApiText(tool.impact, language) && (
                          <p className="mt-1 text-[11.5px] text-slate-600">
                            {t('tools.impact')}: {localizeApiText(tool.impact, language)}
                          </p>
                        )}

                        <p className="mt-1 font-mono text-[11px] text-slate-600">{tool.name}</p>
                      </div>

                      <div className="shrink-0">
                        <Toggle
                          checked={tool.enabled}
                          label=""
                          onChange={(value) =>
                            setEnabled.mutate({ name: tool.name, enabled: value })
                          }
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          ))}

          {(hostAudit.data?.recentTools?.length ?? 0) > 0 && (
            <section>
              <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                {t('tools.hostAudit')}
              </h2>
              <div className="card divide-y divide-uryx-border">
                {hostAudit.data?.recentTools?.slice(0, 12).map((entry) => (
                  <div
                    key={`${entry.name}-${entry.at}`}
                    className="flex items-center gap-3 px-3.5 py-2.5 text-[12.5px]"
                  >
                    <span className="min-w-0 flex-1 truncate font-mono text-slate-300">
                      {entry.name}
                    </span>
                    <span className="shrink-0 text-slate-600">
                      {entry.policy === 'unsafe' ? 'unsafe' : 'safe'}
                    </span>
                    <span className="shrink-0 text-slate-600">{entry.ms} ms</span>
                    <StatusBadge
                      state={entry.success ? 'up' : 'down'}
                      label={entry.success ? t('tool.ok') : t('tool.error')}
                    />
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Geçmiş */}
          <section>
            <h2 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
              <Wrench size={13} />
              {t('tools.recent')}
            </h2>
            <div className="card divide-y divide-uryx-border">
              {history.data?.length === 0 && (
                <p className="p-4 text-[13px] text-slate-500">{t('tools.none')}</p>
              )}
              {(history.data ?? []).slice(0, 25).map((entry) => {
                const status = String(entry.status ?? '');
                return (
                  <div
                    key={String(entry.id)}
                    className="flex items-center gap-3 px-3.5 py-2.5 text-[12.5px]"
                  >
                    <span className="min-w-0 flex-1 truncate font-mono text-slate-300">
                      {String(entry.tool_name)}
                    </span>
                    <span className="shrink-0 text-slate-600">
                      {formatDuration(Number(entry.duration_ms ?? 0), language)}
                    </span>
                    <span className="shrink-0 text-slate-600">
                      {formatRelative(String(entry.created_at), language)}
                    </span>
                    <StatusBadge
                      state={
                        status === 'success' ? 'up' : status === 'rejected' ? 'degraded' : 'down'
                      }
                      label={
                        status === 'success'
                          ? t('tool.ok')
                          : status === 'rejected'
                            ? t('tool.rejected')
                            : t('tool.error')
                      }
                    />
                  </div>
                );
              })}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
