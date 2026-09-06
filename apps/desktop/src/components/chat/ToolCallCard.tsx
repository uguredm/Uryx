/** Araç çağrısı görünümü. */

import { useState } from 'react';
import { createPortal } from 'react-dom';
import {
  Ban,
  Check,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  FolderOpen,
  Loader2,
  Maximize2,
  Wrench,
  X,
} from 'lucide-react';

import {
  displayResultFallback,
  flattenToolArgs,
  mcpResultText,
  summarizedToolStatus,
  toolCardLabel,
  toolCardResult,
} from '@/lib/confirmResponse';
import { cn } from '@/lib/cn';
import { displaySafePath } from '@/lib/displaySafePath';
import { formatDuration } from '@/lib/format';
import { useI18n, type MessageKey } from '@/lib/i18n';
import { localizeApiText, toolDisplayName } from '@/lib/apiText';
import { tNow } from '@/lib/tNow';

export type ToolCallStatus = 'running' | 'success' | 'failed' | 'rejected';

interface Props {
  toolName: string;
  displayName: string;
  args: Record<string, unknown>;
  status: ToolCallStatus;
  result?: Record<string, unknown>;
  error?: string;
  durationMs?: number;
}

const STATUS_KEYS: Record<ToolCallStatus, MessageKey> = {
  running: 'tool.status.running',
  success: 'tool.status.success',
  failed: 'tool.status.failed',
  rejected: 'tool.status.rejected',
};

const STATUS_META: Record<
  ToolCallStatus,
  { icon: typeof Check; className: string }
> = {
  running: { icon: Loader2, className: 'text-uryx-accent' },
  success: { icon: Check, className: 'text-uryx-ok' },
  failed: { icon: X, className: 'text-uryx-danger' },
  rejected: { icon: Ban, className: 'text-uryx-warn' },
};

export function ToolCallCard({
  toolName,
  displayName,
  args,
  status,
  result,
  error,
  durationMs,
}: Props): JSX.Element {
  const { t, language } = useI18n();
  const [expanded, setExpanded] = useState(false);
  const [selectedMedia, setSelectedMedia] = useState<MediaItem | null>(null);
  const displayStatus = summarizedToolStatus(toolName, { status, error, result });
  const meta = STATUS_META[displayStatus];
  const Icon = meta.icon;
  const argEntries = flattenToolArgs(toolName, args, result);
  const title = toolCardLabel(toolName, toolDisplayName(toolName, displayName, language), args, result);
  const bodyText = mcpResultText(toolName, result);
  const shownResult = toolCardResult(toolName, result);
  const fallbackText = bodyText || displayResultFallback(shownResult);
  const hasDetail = argEntries.length > 0 || !!error || Boolean(fallbackText);
  const media = getMedia(shownResult);
  const gallery = [...(media ? [media] : []), ...getResultImages(shownResult)];

  return (
    <div className="overflow-hidden rounded-lg border border-uryx-border bg-uryx-panel/60">
      <button
        type="button"
        onClick={() => hasDetail && setExpanded((value) => !value)}
        className={cn(
          'flex w-full items-center gap-2 px-3 py-2 text-left text-[13px]',
          hasDetail && 'transition-colors hover:bg-white/5',
        )}
        disabled={!hasDetail}
      >
        {hasDetail ? (
          expanded ? (
            <ChevronDown size={13} className="shrink-0 text-slate-500" />
          ) : (
            <ChevronRight size={13} className="shrink-0 text-slate-500" />
          )
        ) : (
          <span className="w-[13px]" />
        )}

        <Wrench size={13} className="shrink-0 text-slate-500" />
        <span className="min-w-0 flex-1 truncate text-slate-200">{title}</span>

        {durationMs !== undefined && displayStatus !== 'running' && (
          <span className="shrink-0 font-mono text-[11px] text-slate-600">
            {formatDuration(durationMs, language)}
          </span>
        )}

        <span className={cn('flex shrink-0 items-center gap-1 text-[11px]', meta.className)}>
          <Icon size={12} className={displayStatus === 'running' ? 'animate-spin' : undefined} />
          {t(STATUS_KEYS[displayStatus])}
        </span>
      </button>

      {gallery.length > 0 && displayStatus === 'success' && (
        <div className="grid grid-cols-2 gap-2 border-t border-uryx-border bg-black/30 p-2 sm:grid-cols-3">
          {gallery.map((item, index) => (
            <button
              key={`${item.url}-${index}`}
              type="button"
              onClick={() => setSelectedMedia(item)}
              className="group relative aspect-video overflow-hidden rounded-md border border-uryx-border bg-black"
              title={item.title || t('action.fullscreen')}
            >
              {item.kind === 'image' ? (
                <img
                  src={item.previewUrl}
                  alt={item.title}
                  className="h-full w-full object-cover"
                />
              ) : (
                <video src={item.url} className="h-full w-full object-cover" preload="metadata" />
              )}
              <span className="absolute right-2 top-2 rounded-md border border-white/10 bg-black/70 p-1.5 text-white opacity-0 transition-opacity group-hover:opacity-100">
                <Maximize2 size={14} />
              </span>
            </button>
          ))}
        </div>
      )}

      {expanded && hasDetail && (
        <div className="space-y-2 border-t border-uryx-border px-3 py-2.5 text-[12px]">
          <p className="font-mono text-[11px] text-slate-600">{toolName}</p>

          {argEntries.length > 0 && (
            <div>
              <p className="mb-1 text-[11px] uppercase tracking-wide text-slate-500">
                {t('tool.params')}
              </p>
              <div className="space-y-0.5">
                {argEntries.map(([key, value]) => (
                  <div key={key} className="flex gap-2">
                    <span className="shrink-0 font-mono text-slate-500">{key}:</span>
                    <span className="min-w-0 flex-1 break-all font-mono text-slate-300">
                      {typeof value === 'string' ? displaySafePath(value) || value : JSON.stringify(value)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {error && (
            <div>
              <p className="mb-1 text-[11px] uppercase tracking-wide text-slate-500">{t('hud.state.error')}</p>
              <p className="break-words text-rose-300">
                {localizeApiText(error, language) || error}
              </p>
            </div>
          )}

          {fallbackText && (
            <div>
              <p className="mb-1 text-[11px] uppercase tracking-wide text-slate-500">{t('tool.result')}</p>
              <pre
                className={cn(
                  'max-h-56 overflow-auto whitespace-pre-wrap rounded border border-uryx-border bg-black/40 p-2 font-mono text-[11px]',
                  displayStatus === 'failed' ? 'text-rose-300' : 'text-slate-300',
                )}
              >
                {fallbackText.includes('\\Users\\') || fallbackText.includes('/Users/')
                  ? displaySafePath(fallbackText) || fallbackText
                  : fallbackText}
              </pre>
            </div>
          )}
        </div>
      )}

      {selectedMedia &&
        createPortal(
          <div
            className="fixed inset-0 z-[100] flex items-center justify-center bg-black/90 p-6"
            role="dialog"
            aria-modal="true"
            onClick={() => setSelectedMedia(null)}
          >
            <div className="absolute right-5 top-5 flex gap-2">
              {selectedMedia.path && (
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    void window.uryx?.shell.showItemInFolder(selectedMedia.path!);
                  }}
                  className="rounded-md border border-white/15 bg-black/70 p-2 text-white hover:bg-white/10"
                  title={t('action.openFolder')}
                >
                  <FolderOpen size={18} />
                </button>
              )}
              {selectedMedia.source && (
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    window.open(selectedMedia.source, '_blank', 'noopener,noreferrer');
                  }}
                  className="rounded-md border border-white/15 bg-black/70 p-2 text-white hover:bg-white/10"
                  title={t('action.openSource')}
                >
                  <ExternalLink size={18} />
                </button>
              )}
              <button
                type="button"
                onClick={() => setSelectedMedia(null)}
                className="rounded-md border border-white/15 bg-black/70 p-2 text-white hover:bg-white/10"
                title={t('action.close')}
              >
                <X size={18} />
              </button>
            </div>
            {selectedMedia.kind === 'image' ? (
              <img
                src={selectedMedia.url}
                alt={selectedMedia.title}
                className="max-h-full max-w-full object-contain"
                onClick={(event) => event.stopPropagation()}
              />
            ) : (
              <video
                src={selectedMedia.url}
                className="max-h-full max-w-full"
                controls
                autoPlay
                onClick={(event) => event.stopPropagation()}
              />
            )}
          </div>,
          document.body,
        )}
    </div>
  );
}

const IMAGE_EXTENSIONS = new Set(['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp']);
const VIDEO_EXTENSIONS = new Set(['mp4', 'webm', 'mov', 'm4v']);

interface MediaItem {
  path?: string;
  source?: string;
  title: string;
  url: string;
  previewUrl: string;
  kind: 'image' | 'video';
}

function getMedia(result?: Record<string, unknown>): MediaItem | null {
  const filePath = typeof result?.path === 'string' ? result.path : '';
  const extension = filePath.split('.').pop()?.toLowerCase() ?? '';
  const kind = IMAGE_EXTENSIONS.has(extension)
    ? 'image'
    : VIDEO_EXTENSIONS.has(extension)
      ? 'video'
      : null;
  if (!kind) return null;
  return {
    path: filePath,
    url: `uryx-media://local/?path=${encodeURIComponent(filePath)}`,
    previewUrl: `uryx-media://local/?path=${encodeURIComponent(filePath)}`,
    title: filePath.split(/[\\/]/).pop() ?? tNow('tool.media'),
    kind,
  };
}

function getResultImages(result?: Record<string, unknown>): MediaItem[] {
  if (!Array.isArray(result?.images)) return [];
  return result.images.flatMap((value) => {
    if (!value || typeof value !== 'object') return [];
    const image = value as Record<string, unknown>;
    const filePath = typeof image.path === 'string' ? image.path : '';
    const extension = filePath.split('.').pop()?.toLowerCase() ?? '';
    if (filePath && IMAGE_EXTENSIONS.has(extension)) {
      const localUrl = `uryx-media://local/?path=${encodeURIComponent(filePath)}`;
      return [
        {
          path: filePath,
          title: typeof image.title === 'string' ? image.title : tNow('tool.webImage'),
          url: localUrl,
          previewUrl: localUrl,
          source: typeof image.source === 'string' ? image.source : undefined,
          kind: 'image' as const,
        },
      ];
    }
    const url = typeof image.image === 'string' ? image.image : '';
    if (!url.startsWith('https://')) return [];
    const preview = typeof image.thumbnail === 'string' ? image.thumbnail : url;
    return [
      {
        title: typeof image.title === 'string' ? image.title : tNow('tool.searchImage'),
        url,
        previewUrl: preview.startsWith('https://') ? preview : url,
        source: typeof image.source === 'string' ? image.source : undefined,
        kind: 'image' as const,
      },
    ];
  });
}
