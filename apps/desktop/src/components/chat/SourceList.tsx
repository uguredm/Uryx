/** Cevabın altında gösterilen RAG kaynakları. */

import { useState } from 'react';
import { ChevronDown, ChevronRight, FileText } from 'lucide-react';
import type { SourceRef } from '@shared/api';

import { truncate } from '@/lib/format';
import { useI18n } from '@/lib/i18n';

export function SourceList({ sources }: { sources: SourceRef[] }): JSX.Element | null {
  const { t } = useI18n();
  const [expanded, setExpanded] = useState(false);
  if (!sources.length) return null;

  return (
    <div className="mt-2 w-full">
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className="flex items-center gap-1.5 text-[11px] text-slate-500 transition-colors hover:text-slate-300"
      >
        {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        <FileText size={12} />
        {t('source.used', { n: sources.length })}
      </button>

      {expanded && (
        <div className="mt-1.5 space-y-1.5">
          {sources.map((source, index) => (
            <div
              key={source.chunk_id}
              className="rounded-lg border border-uryx-border bg-uryx-panel/50 p-2.5"
            >
              <div className="flex items-baseline gap-2">
                <span className="shrink-0 font-mono text-[11px] text-uryx-accent">
                  [{index + 1}]
                </span>
                <span className="min-w-0 flex-1 truncate text-[12px] font-medium text-slate-200">
                  {source.filename}
                  {source.page ? ` · ${t('panel.page', { page: source.page })}` : ''}
                </span>
                <span className="shrink-0 font-mono text-[10.5px] text-slate-600">
                  {(source.score * 100).toFixed(0)}%
                </span>
              </div>
              <p className="mt-1 text-[12px] leading-relaxed text-slate-400">
                {truncate(source.snippet, 260)}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
