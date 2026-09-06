/** Belge / RAG yönetimi: yükle, sürükle-bırak, klasör ekle, indeks durumu. */

import { useCallback, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertCircle,
  FileText,
  FolderOpen,
  Loader2,
  RefreshCw,
  Search,
  Trash2,
  Upload,
} from 'lucide-react';

import { EmptyState, ErrorBox, Loading, ViewHeader } from '@/components/common/Primitives';
import { api } from '@/lib/api';
import { cn } from '@/lib/cn';
import { documentStatusLabel, formatBytes, formatRelative, truncate } from '@/lib/format';
import { useI18n } from '@/lib/i18n';
import { useUIStore } from '@/stores/uiStore';

export function DocumentsView(): JSX.Element {
  const { t, language } = useI18n();
  const [dragging, setDragging] = useState(false);
  const [query, setQuery] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  const queryClient = useQueryClient();
  const pushToast = useUIStore((state) => state.pushToast);

  const documents = useQuery({
    queryKey: ['documents'],
    queryFn: () => api.documents.list(),
    refetchInterval: (result) =>
      result.state.data?.some((doc) => ['pending', 'parsing', 'embedding'].includes(doc.status))
        ? 2500
        : false,
  });

  const stats = useQuery({ queryKey: ['document-stats'], queryFn: () => api.documents.stats() });
  const supported = useQuery({
    queryKey: ['supported-extensions'],
    queryFn: () => api.documents.supported(),
    staleTime: Infinity,
  });

  const searchResults = useQuery({
    queryKey: ['document-search', query],
    queryFn: () => api.documents.search(query, 8),
    enabled: query.trim().length > 2,
  });

  const refresh = (): void => {
    void queryClient.invalidateQueries({ queryKey: ['documents'] });
    void queryClient.invalidateQueries({ queryKey: ['document-stats'] });
  };

  const upload = useMutation({
    mutationFn: (files: File[]) => api.documents.upload(files),
    onSuccess: (result) => {
      refresh();
      const accepted = result.accepted.length;
      const duplicates = result.duplicates.length;
      const failed = result.failed.length;
      const parts = [t('docs.queued', { n: accepted })];
      if (duplicates) parts.push(t('docs.already', { n: duplicates }));
      if (failed) parts.push(t('docs.failedCount', { n: failed }));
      pushToast(failed ? 'warning' : 'success', parts.join(' · '));
    },
    onError: (error) =>
      pushToast('error', error instanceof Error ? error.message : t('docs.uploadFail')),
  });

  const reindex = useMutation({
    mutationFn: (id: string) => api.documents.reindex(id),
    onSuccess: () => {
      refresh();
      pushToast('info', t('docs.reindexStart'));
    },
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.documents.remove(id),
    onSuccess: () => {
      refresh();
      pushToast('success', t('docs.deleted'));
    },
  });

  const handleFiles = useCallback(
    (fileList: FileList | null) => {
      const files = Array.from(fileList ?? []);
      if (files.length) upload.mutate(files);
    },
    [upload],
  );

  const pickFolder = (): void => folderInputRef.current?.click();

  const busy = upload.isPending;

  return (
    <div
      className="flex h-full min-h-0 flex-col"
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={(event) => {
        if (event.currentTarget === event.target) setDragging(false);
      }}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        handleFiles(event.dataTransfer.files);
      }}
    >
      <ViewHeader
        title={t('view.documents')}
        description={
          stats.data
            ? t('docs.stats', {
                total: stats.data.total,
                chunks: stats.data.total_chunks,
                size: formatBytes(stats.data.total_size_bytes, language),
              })
            : t('view.documents.desc')
        }
        actions={
          <>
            <button
              type="button"
              className="btn-outline"
              onClick={() => void pickFolder()}
              disabled={busy}
            >
              <FolderOpen size={15} />
              {t('docs.addFolder')}
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={() => fileInputRef.current?.click()}
              disabled={busy}
            >
              {busy ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />}
              {t('docs.upload')}
            </button>
          </>
        }
      />

      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        accept={supported.data?.extensions.join(',')}
        onChange={(event) => {
          handleFiles(event.target.files);
          event.target.value = '';
        }}
      />
      <input
        ref={folderInputRef}
        type="file"
        multiple
        className="hidden"
        accept={supported.data?.extensions.join(',')}
        {...{ webkitdirectory: '' }}
        onChange={(event) => {
          handleFiles(event.target.files);
          event.target.value = '';
        }}
      />

      {/* Arama */}
      <div className="shrink-0 border-b border-uryx-border px-6 py-3">
        <div className="relative max-w-xl">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t('docs.searchPh')}
            className="input pl-8"
          />
        </div>
      </div>

      <div className="scroll-area flex-1 p-6">
        {/* Embedding fallback uyarısı */}
        {stats.data?.embedding_fallback && (
          <div className="mx-auto mb-4 flex max-w-4xl items-start gap-2.5 rounded-lg border border-uryx-warn/40 bg-uryx-warn/10 p-3">
            <AlertCircle size={16} className="mt-0.5 shrink-0 text-uryx-warn" />
            <p className="text-[12.5px] leading-relaxed text-amber-200">{t('docs.embedFallback')}</p>
          </div>
        )}

        {/* Arama sonuçları */}
        {query.trim().length > 2 && (
          <div className="mx-auto mb-6 max-w-4xl">
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
              {t('docs.searchResults')}
            </h2>
            {searchResults.isLoading && <Loading label={t('docs.searching')} />}
            {searchResults.data?.length === 0 && (
              <p className="text-[13px] text-slate-500">{t('docs.noHits')}</p>
            )}
            <div className="space-y-2">
              {searchResults.data?.map((hit) => (
                <div key={hit.chunk_id} className="card p-3">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="truncate text-[13px] font-medium text-slate-200">
                      {hit.filename}
                      {hit.page ? ` · ${t('panel.page', { page: hit.page })}` : ''}
                    </span>
                    <span className="shrink-0 font-mono text-[11px] text-uryx-accent">
                      {(hit.score * 100).toFixed(0)}%
                    </span>
                  </div>
                  <p className="mt-1 text-[12.5px] leading-relaxed text-slate-400">
                    {truncate(hit.content, 320)}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Belge listesi */}
        {documents.isLoading && <Loading label={t('docs.loading')} />}

        {documents.isError && (
          <ErrorBox
            message={
              documents.error instanceof Error ? documents.error.message : t('docs.loadFail')
            }
            action={
              <button
                type="button"
                className="btn-outline"
                onClick={() => void documents.refetch()}
              >
                {t('action.retry')}
              </button>
            }
          />
        )}

        {documents.data?.length === 0 && (
          <EmptyState
            icon={<FileText size={36} />}
            title={t('docs.empty')}
            description={t('docs.emptyDesc', {
              types: supported.data?.extensions.slice(0, 14).join(', ') ?? 'pdf, docx, txt, md…',
            })}
          />
        )}

        <div className="mx-auto max-w-4xl space-y-2">
          {documents.data?.map((document) => {
            const processing = ['pending', 'parsing', 'embedding'].includes(document.status);
            return (
              <div key={document.id} className="card p-3">
                <div className="flex items-start gap-3">
                  <FileText size={16} className="mt-0.5 shrink-0 text-slate-500" />

                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[13.5px] text-slate-200">{document.filename}</p>
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-[11.5px] text-slate-500">
                      <span
                        className={cn(
                          'badge',
                          document.status === 'indexed'
                            ? 'bg-uryx-ok/15 text-uryx-ok'
                            : document.status === 'failed'
                              ? 'bg-uryx-danger/15 text-uryx-danger'
                              : 'bg-uryx-warn/15 text-uryx-warn',
                        )}
                      >
                        {processing && <Loader2 size={10} className="animate-spin" />}
                        {documentStatusLabel(document.status, language)}
                      </span>
                      <span>{formatBytes(document.size_bytes, language)}</span>
                      {document.chunk_count > 0 && (
                        <>
                          <span>·</span>
                          <span>{t('docs.chunks', { n: document.chunk_count })}</span>
                        </>
                      )}
                      <span>·</span>
                      <span>{formatRelative(document.created_at, language)}</span>
                    </div>
                    {document.error && (
                      <p className="mt-1 text-[11.5px] text-rose-300">{document.error}</p>
                    )}
                  </div>

                  <div className="flex shrink-0 gap-1">
                    <button
                      type="button"
                      onClick={() => reindex.mutate(document.id)}
                      disabled={processing}
                      className="rounded-md p-1.5 text-slate-500 transition-colors hover:bg-white/5 hover:text-slate-300 disabled:opacity-40"
                      title={t('action.reindex')}
                    >
                      <RefreshCw size={14} />
                    </button>
                    <button
                      type="button"
                      onClick={() => remove.mutate(document.id)}
                      className="rounded-md p-1.5 text-slate-500 transition-colors hover:bg-uryx-danger/15 hover:text-uryx-danger"
                      title={t('action.delete')}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Sürükle-bırak katmanı */}
      {dragging && (
        <div className="pointer-events-none fixed inset-0 z-30 flex items-center justify-center bg-uryx-bg/85 backdrop-blur-sm">
          <div className="rounded-2xl border-2 border-dashed border-uryx-accent px-12 py-10 text-center">
            <Upload size={36} className="mx-auto text-uryx-accent" />
            <p className="mt-3 text-sm font-medium text-slate-100">
              {t('docs.drop')}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
