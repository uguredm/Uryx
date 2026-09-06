/** Hafıza yönetimi ekranı: görüntüle, düzenle, sil, sabitle, manuel ekle. */

import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Pin, PinOff, Plus, RefreshCw, Search, Sparkles, Trash2, X } from 'lucide-react';
import type { MemoryCategory } from '@shared/api';

import { EmptyState, ErrorBox, Loading, ViewHeader } from '@/components/common/Primitives';
import { api } from '@/lib/api';
import { cn } from '@/lib/cn';
import { formatRelative, memoryCategoryLabel } from '@/lib/format';
import { useI18n } from '@/lib/i18n';
import { useUIStore } from '@/stores/uiStore';

const CATEGORIES: MemoryCategory[] = [
  'preference',
  'system_info',
  'project',
  'folder',
  'application',
  'contact',
  'fact',
  'other',
];

export function MemoryView(): JSX.Element {
  const { t, language } = useI18n();
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState<string>('');
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState('');

  const queryClient = useQueryClient();
  const pushToast = useUIStore((state) => state.pushToast);

  const memories = useQuery({
    queryKey: ['memories', search, category],
    queryFn: () => api.memory.list({ q: search || undefined, category: category || undefined }),
  });
  const stats = useQuery({ queryKey: ['memory-stats'], queryFn: () => api.memory.stats() });

  const refresh = (): void => {
    void queryClient.invalidateQueries({ queryKey: ['memories'] });
    void queryClient.invalidateQueries({ queryKey: ['memory-stats'] });
  };

  const create = useMutation({
    mutationFn: (payload: { content: string; category: string }) => api.memory.create(payload),
    onSuccess: () => {
      refresh();
      setAdding(false);
      setDraft('');
      pushToast('success', t('memory.added'));
    },
    onError: (error) =>
      pushToast('error', error instanceof Error ? error.message : t('memory.addFail')),
  });

  const update = useMutation({
    mutationFn: ({ id, content }: { id: string; content: string }) =>
      api.memory.update(id, { content }),
    onSuccess: () => {
      refresh();
      setEditingId(null);
      pushToast('success', t('memory.updated'));
    },
    onError: (error) =>
      pushToast('error', error instanceof Error ? error.message : t('memory.updateFail')),
  });

  const pin = useMutation({
    mutationFn: ({ id, pinned }: { id: string; pinned: boolean }) => api.memory.pin(id, pinned),
    onSuccess: refresh,
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.memory.remove(id),
    onSuccess: () => {
      refresh();
      pushToast('success', t('memory.deleted'));
    },
  });

  const reindex = useMutation({
    mutationFn: () => api.memory.reindex(),
    onSuccess: (result) => pushToast('success', result.message ?? t('memory.reindexed')),
    onError: (error) =>
      pushToast('error', error instanceof Error ? error.message : t('memory.indexFail')),
  });

  return (
    <div className="flex h-full min-h-0 flex-col">
      <ViewHeader
        title={t('view.memory')}
        description={
          stats.data
            ? t('memory.stats', { total: stats.data.total, pinned: stats.data.pinned })
            : t('view.memory.desc')
        }
        actions={
          <>
            <button
              type="button"
              className="btn-outline"
              onClick={() => reindex.mutate()}
              disabled={reindex.isPending}
              title={t('memory.reindexTitle')}
            >
              <RefreshCw size={14} className={reindex.isPending ? 'animate-spin' : undefined} />
              {t('action.reindex')}
            </button>
            <button type="button" className="btn-primary" onClick={() => setAdding((v) => !v)}>
              <Plus size={15} />
              {t('memory.new')}
            </button>
          </>
        }
      />

      {/* Filtreler */}
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-uryx-border px-6 py-3">
        <div className="relative">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder={t('memory.search')}
            className="input w-64 pl-8"
          />
        </div>
        <select
          value={category}
          onChange={(event) => setCategory(event.target.value)}
          className="input w-48"
        >
          <option value="">{t('memory.allCats')}</option>
          {CATEGORIES.map((value) => (
            <option key={value} value={value}>
              {memoryCategoryLabel(value, language)}
            </option>
          ))}
        </select>
      </div>

      <div className="scroll-area flex-1 p-6">
        {/* Ekleme formu */}
        {adding && (
          <div className="mx-auto mb-4 max-w-3xl card p-4">
            <p className="label">{t('memory.newRecord')}</p>
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              rows={3}
              placeholder={t('memory.placeholder')}
              className="input resize-none"
            />
            <div className="mt-2 flex items-center gap-2">
              <select id="new-memory-category" className="input w-48" defaultValue="other">
                {CATEGORIES.map((value) => (
                  <option key={value} value={value}>
                    {memoryCategoryLabel(value, language)}
                  </option>
                ))}
              </select>
              <div className="flex-1" />
              <button type="button" className="btn-ghost" onClick={() => setAdding(false)}>
                {t('action.cancel')}
              </button>
              <button
                type="button"
                className="btn-primary"
                disabled={draft.trim().length < 3 || create.isPending}
                onClick={() => {
                  const select = document.getElementById(
                    'new-memory-category',
                  ) as HTMLSelectElement | null;
                  create.mutate({ content: draft.trim(), category: select?.value ?? 'other' });
                }}
              >
                {t('action.save')}
              </button>
            </div>
          </div>
        )}

        {memories.isLoading && <Loading label={t('memory.loading')} />}

        {memories.isError && (
          <ErrorBox
            message={
              memories.error instanceof Error ? memories.error.message : t('memory.loadFail')
            }
            action={
                <button type="button" className="btn-outline" onClick={() => void memories.refetch()}>
                {t('action.retry')}
              </button>
            }
          />
        )}

        {memories.data?.length === 0 && (
          <EmptyState
            icon={<Sparkles size={36} />}
            title={t('memory.empty')}
            description={t('memory.emptyHint')}
          />
        )}

        <div className="mx-auto max-w-3xl space-y-2">
          {memories.data?.map((memory) => (
            <div key={memory.id} className="card p-3.5">
              <div className="flex items-start gap-3">
                <div className="min-w-0 flex-1">
                  {editingId === memory.id ? (
                    <textarea
                      value={draft}
                      onChange={(event) => setDraft(event.target.value)}
                      rows={3}
                      className="input resize-none"
                      autoFocus
                    />
                  ) : (
                    <p className="text-[13.5px] leading-relaxed text-slate-200">{memory.content}</p>
                  )}

                  <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
                    <span className="badge bg-white/5 text-slate-400">
                      {memoryCategoryLabel(memory.category, language)}
                    </span>
                    <span>{t('memory.importance', { pct: (memory.importance * 100).toFixed(0) })}</span>
                    <span>·</span>
                    <span>{memory.source === 'auto' ? 'Otomatik' : 'Elle eklendi'}</span>
                    <span>·</span>
                    <span>{formatRelative(memory.created_at, language)}</span>
                    {memory.use_count > 0 && (
                      <>
                        <span>·</span>
                        <span>{t('memory.usedCount', { n: memory.use_count })}</span>
                      </>
                    )}
                  </div>
                </div>

                {/* Eylemler */}
                <div className="flex shrink-0 gap-1">
                  {editingId === memory.id ? (
                    <>
                      <button
                        type="button"
                        onClick={() => update.mutate({ id: memory.id, content: draft.trim() })}
                        disabled={draft.trim().length < 3}
                        className="rounded-md p-1.5 text-uryx-ok transition-colors hover:bg-uryx-ok/15"
                        title={t('action.save')}
                      >
                        <Check size={14} />
                      </button>
                      <button
                        type="button"
                        onClick={() => setEditingId(null)}
                        className="rounded-md p-1.5 text-slate-500 transition-colors hover:bg-white/5"
                        title={t('action.cancel')}
                      >
                        <X size={14} />
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        type="button"
                        onClick={() => pin.mutate({ id: memory.id, pinned: !memory.pinned })}
                        className={cn(
                          'rounded-md p-1.5 transition-colors hover:bg-white/5',
                          memory.pinned ? 'text-uryx-accent' : 'text-slate-500',
                        )}
                        title={memory.pinned ? t('hud.action.unpin') : t('action.pin')}
                      >
                        {memory.pinned ? <Pin size={14} /> : <PinOff size={14} />}
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setEditingId(memory.id);
                          setDraft(memory.content);
                        }}
                        className="rounded-md px-2 py-1.5 text-[11px] text-slate-500 transition-colors hover:bg-white/5 hover:text-slate-300"
                      >
                        {t('memory.edit')}
                      </button>
                      <button
                        type="button"
                        onClick={() => remove.mutate(memory.id)}
                        className="rounded-md p-1.5 text-slate-500 transition-colors hover:bg-uryx-danger/15 hover:text-uryx-danger"
                        title={t('action.delete')}
                      >
                        <Trash2 size={14} />
                      </button>
                    </>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
