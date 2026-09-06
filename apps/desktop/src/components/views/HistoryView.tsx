/** Sohbet geçmişi — Open WebUI Ctrl+K + LibreChat anlık arama. */

import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Download, MessageSquare, Pencil, Pin, PinOff, Search, Trash2 } from 'lucide-react';
import type { ConversationSummary } from '@shared/api';

import { EmptyState, ErrorBox, Loading, ViewHeader } from '@/components/common/Primitives';
import { api } from '@/lib/api';
import { formatRelative } from '@/lib/format';
import { useI18n, type MessageKey } from '@/lib/i18n';
import {
  debounceMs,
  groupConversations,
  searchHitWithNeighbors,
  splitHighlight,
  stepHistoryIndex,
  type HistoryBucket,
  type SearchHit,
} from '@/lib/historySearch';
import { splitPinnedConversations, usePinnedChatsStore } from '@/lib/pinnedChats';
import { exportConversationMarkdown } from '@/lib/exportConversation';
import { sanitizeRenameTitle } from '@/lib/renameConversation';
import { useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';

const HISTORY_BUCKET_KEY: Record<HistoryBucket, MessageKey> = {
  today: 'history.bucket.today',
  yesterday: 'history.bucket.yesterday',
  week: 'history.bucket.week',
  older: 'history.bucket.older',
};

export function HistoryView(): JSX.Element {
  const { t } = useI18n();
  const [draft, setDraft] = useState('');
  const [query, setQuery] = useState('');
  const [snippets, setSnippets] = useState<Record<string, SearchHit>>({});
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const pinnedIds = usePinnedChatsStore((state) => state.ids);
  const togglePin = usePinnedChatsStore((state) => state.toggle);
  const unpin = usePinnedChatsStore((state) => state.unpin);
  const searchRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();
  const loadConversation = useChatStore((state) => state.loadConversation);
  const activeId = useChatStore((state) => state.conversationId);
  const setView = useUIStore((state) => state.setView);
  const pushToast = useUIStore((state) => state.pushToast);
  const historySearchTick = useUIStore((state) => state.historySearchTick);

  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(draft.trim()), debounceMs(draft));
    return () => window.clearTimeout(timer);
  }, [draft]);

  useEffect(() => {
    searchRef.current?.focus();
    searchRef.current?.select();
  }, [historySearchTick]);

  const conversations = useQuery({
    queryKey: ['conversations', query],
    queryFn: () => api.conversations.list(query || undefined),
  });

  const { pinned, rest } = useMemo(
    () => splitPinnedConversations(conversations.data ?? [], pinnedIds),
    [conversations.data, pinnedIds],
  );
  const groups = useMemo(() => groupConversations(rest), [rest]);
  const showPinned = !query && pinned.length > 0;
  const visibleIds = useMemo(() => {
    const groupedIds = groups.flatMap((group) => group.items.map((item) => item.id));
    return showPinned ? [...pinned.map((item) => item.id), ...groupedIds] : groupedIds;
  }, [showPinned, pinned, groups]);

  useEffect(() => {
    setSelectedIndex(-1);
  }, [query, conversations.data]);

  useEffect(() => {
    if (!query || !conversations.data?.length) {
      setSnippets({});
      return;
    }
    let cancelled = false;
    const ids = conversations.data.slice(0, 8).map((item) => item.id);
    void Promise.all(
      ids.map(async (id) => {
        try {
          const detail = await api.conversations.get(id);
          const hit = searchHitWithNeighbors(detail.messages, query);
          return [id, hit] as const;
        } catch {
          return [id, null] as const;
        }
      }),
    ).then((rows) => {
      if (cancelled) return;
      setSnippets(
        Object.fromEntries(
          rows.filter((row): row is [string, SearchHit] => row[1] !== null),
        ),
      );
    });
    return () => {
      cancelled = true;
    };
  }, [query, conversations.data]);

  const exportChat = useMutation({
    mutationFn: async ({ id, title }: { id: string; title: string }) => {
      const detail = await api.conversations.get(id);
      const ok = await exportConversationMarkdown({
        title: title || detail.title,
        messages: detail.messages,
      });
      if (!ok) throw new Error(t('toast.exportEmpty'));
    },
    onSuccess: () => pushToast('success', t('toast.exportOk')),
    onError: (error) =>
      pushToast('error', error instanceof Error ? error.message : t('history.exportFail')),
  });

  const rename = useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) => api.conversations.rename(id, title),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['conversations'] });
      pushToast('success', t('history.renameOk'));
    },
    onError: (error) =>
      pushToast('error', error instanceof Error ? error.message : t('history.renameFail')),
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.conversations.remove(id),
    onSuccess: (_ok, id) => {
      unpin(id);
      void queryClient.invalidateQueries({ queryKey: ['conversations'] });
      pushToast('success', t('history.deleteOk'));
    },
    onError: (error) =>
      pushToast('error', error instanceof Error ? error.message : t('history.deleteFail')),
  });

  const selectedId = selectedIndex >= 0 ? visibleIds[selectedIndex] : undefined;

  const open = async (id: string): Promise<void> => {
    try {
      await loadConversation(id);
      setView('chat');
    } catch (error) {
      pushToast('error', error instanceof Error ? error.message : t('history.openFail'));
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <ViewHeader
        title={t('view.history')}
        description={t('view.history.desc')}
        actions={
          <div className="relative">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              ref={searchRef}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                  event.preventDefault();
                  setSelectedIndex((current) =>
                    stepHistoryIndex(current, event.key === 'ArrowDown' ? 1 : -1, visibleIds.length),
                  );
                  return;
                }
                if (event.key === 'Enter' && selectedIndex >= 0) {
                  const id = visibleIds[selectedIndex];
                  if (id) {
                    event.preventDefault();
                    void open(id);
                  }
                }
              }}
              placeholder={t('history.search')}
              className="input w-64 pl-8"
              aria-label={t('history.searchAria')}
            />
          </div>
        }
      />

      <div className="scroll-area flex-1 p-6">
        {conversations.isLoading && <Loading label={t('history.loading')} />}

        {conversations.isError && (
          <ErrorBox
            message={
              conversations.error instanceof Error
                ? conversations.error.message
                : t('history.loadFail')
            }
            action={
              <button type="button" className="btn-outline" onClick={() => void conversations.refetch()}>
                {t('action.retry')}
              </button>
            }
          />
        )}

        {conversations.data && conversations.data.length === 0 && (
          <EmptyState
            icon={<MessageSquare size={36} />}
            title={query ? t('history.emptyQuery') : t('history.empty')}
            description={query ? t('history.emptyQueryHint') : t('history.emptyHint')}
          />
        )}

        <div className="mx-auto max-w-3xl space-y-5">
          {showPinned && (
            <section>
              <h2 className="mb-2 text-[11px] font-medium uppercase tracking-wide text-slate-500">
                {t('history.pinned')}
              </h2>
              <div className="space-y-2">
                {pinned.map((conversation) => (
                  <HistoryRow
                    key={conversation.id}
                    conversation={conversation}
                    query={query}
                    hit={snippets[conversation.id]}
                    active={activeId === conversation.id}
                    selected={selectedId === conversation.id}
                    pinned
                    deleting={remove.isPending}
                    onOpen={() => void open(conversation.id)}
                    onPin={() => togglePin(conversation.id)}
                    onRename={(title) => rename.mutate({ id: conversation.id, title })}
                    onExport={() =>
                      exportChat.mutate({ id: conversation.id, title: conversation.title })
                    }
                    onRemove={() => remove.mutate(conversation.id)}
                  />
                ))}
              </div>
            </section>
          )}
          {groups.map(({ bucket, items }) => (
            <section key={bucket}>
              <h2 className="mb-2 text-[11px] font-medium uppercase tracking-wide text-slate-500">
                {t(HISTORY_BUCKET_KEY[bucket])}
              </h2>
              <div className="space-y-2">
                {items.map((conversation) => (
                  <HistoryRow
                    key={conversation.id}
                    conversation={conversation}
                    query={query}
                    hit={snippets[conversation.id]}
                    active={activeId === conversation.id}
                    selected={selectedId === conversation.id}
                    pinned={false}
                    deleting={remove.isPending}
                    onOpen={() => void open(conversation.id)}
                    onPin={() => togglePin(conversation.id)}
                    onRename={(title) => rename.mutate({ id: conversation.id, title })}
                    onExport={() =>
                      exportChat.mutate({ id: conversation.id, title: conversation.title })
                    }
                    onRemove={() => remove.mutate(conversation.id)}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}

function HistoryRow({
  conversation,
  query,
  hit,
  active,
  selected,
  pinned,
  deleting,
  onOpen,
  onPin,
  onRename,
  onExport,
  onRemove,
}: {
  conversation: ConversationSummary;
  query: string;
  hit?: SearchHit;
  active: boolean;
  selected: boolean;
  pinned: boolean;
  deleting: boolean;
  onOpen: () => void;
  onPin: () => void;
  onRename: (title: string) => void;
  onExport: () => void;
  onRemove: () => void;
}): JSX.Element {
  const { t, language } = useI18n();
  const [editing, setEditing] = useState(false);
  const [draftTitle, setDraftTitle] = useState(conversation.title);

  const commitRename = (): void => {
    const next = sanitizeRenameTitle(draftTitle);
    setEditing(false);
    if (!next || next === conversation.title) {
      setDraftTitle(conversation.title);
      return;
    }
    onRename(next);
  };

  return (
    <div
      className={`card flex items-center gap-3 p-3 transition-colors hover:border-uryx-accent/40 ${
        selected ? 'border-uryx-accent/70 bg-uryx-accent/5' : active ? 'border-uryx-accent/60' : ''
      }`}
    >
      <button
        type="button"
        onClick={() => {
          if (!editing) onOpen();
        }}
        className="flex min-w-0 flex-1 items-center gap-3 text-left"
      >
        <MessageSquare size={16} className="shrink-0 text-slate-500" />
        <span className="min-w-0 flex-1">
          {editing ? (
            <input
              value={draftTitle}
              onChange={(event) => setDraftTitle(event.target.value)}
              onClick={(event) => event.stopPropagation()}
              onKeyDown={(event) => {
                event.stopPropagation();
                if (event.key === 'Enter') {
                  event.preventDefault();
                  commitRename();
                } else if (event.key === 'Escape') {
                  event.preventDefault();
                  setDraftTitle(conversation.title);
                  setEditing(false);
                }
              }}
              onBlur={commitRename}
              className="input w-full py-0.5 text-sm"
              aria-label={t('history.editTitle')}
              autoFocus
            />
          ) : (
          <span className="block truncate text-sm text-slate-200">
            {splitHighlight(conversation.title, query).map((part, index) => (
              <span
                key={`${conversation.id}-${index}`}
                className={part.hit ? 'bg-uryx-accent/25 text-slate-50' : undefined}
              >
                {part.text}
              </span>
            ))}
          </span>
          )}
          <span className="mt-0.5 block text-[11.5px] text-slate-500">
            {t('history.messages', { n: conversation.message_count })} ·{' '}
            {formatRelative(conversation.updated_at, language)}
          </span>
          {hit && (
            <span className="mt-1 block space-y-0.5 text-[12px] leading-snug">
              {hit.before && (
                <span className="block truncate text-slate-600">{hit.before}</span>
              )}
              <span className="block text-slate-400">
                {splitHighlight(hit.snippet, query).map((part, index) => (
                  <span
                    key={`${conversation.id}-snip-${index}`}
                    className={part.hit ? 'bg-uryx-accent/25 text-slate-50' : undefined}
                  >
                    {part.text}
                  </span>
                ))}
              </span>
              {hit.after && (
                <span className="block truncate text-slate-600">{hit.after}</span>
              )}
            </span>
          )}
        </span>
      </button>

      <button
        type="button"
        onClick={() => {
          setDraftTitle(conversation.title);
          setEditing(true);
        }}
        className="shrink-0 rounded-md p-1.5 text-slate-500 transition-colors hover:bg-white/5 hover:text-slate-300"
        title={t('action.rename')}
        aria-label={t('action.rename')}
      >
        <Pencil size={14} />
      </button>

      <button
        type="button"
        onClick={onExport}
        className="shrink-0 rounded-md p-1.5 text-slate-500 transition-colors hover:bg-white/5 hover:text-slate-300"
        title={t('action.exportMd')}
        aria-label={t('action.exportMd')}
      >
        <Download size={14} />
      </button>

      <button
        type="button"
        onClick={onPin}
        className={`shrink-0 rounded-md p-1.5 transition-colors hover:bg-white/5 ${
          pinned ? 'text-uryx-accent' : 'text-slate-500'
        }`}
        title={pinned ? t('hud.action.unpin') : t('action.pin')}
        aria-label={pinned ? t('hud.action.unpin') : t('action.pin')}
      >
        {pinned ? <Pin size={14} /> : <PinOff size={14} />}
      </button>

      <button
        type="button"
        onClick={onRemove}
        disabled={deleting}
        className="shrink-0 rounded-md p-1.5 text-slate-500 transition-colors hover:bg-uryx-danger/15 hover:text-uryx-danger"
        title={t('history.deleteChat')}
        aria-label={t('history.deleteChat')}
      >
        <Trash2 size={14} />
      </button>
    </div>
  );
}
