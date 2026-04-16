'use client';

import { useState } from 'react';
import { BarChart3, BookOpen, ChevronDown, ChevronUp, FileText, Image as ImageIcon, MapPinned, Sparkles } from 'lucide-react';

import { cleanEvidenceTitle } from './evidence';
import type { EvidenceSource } from './evidence';

interface EvidenceCardProps {
  source: EvidenceSource;
  index?: number;
  onOpen?: (source: EvidenceSource) => void;
  compact?: boolean;
}

function locatorLabel(source: EvidenceSource) {
  const { page, line_start, line_end } = source;
  if (line_start && line_end) {
    const pagePart =
      typeof page === 'number'
        ? `第 ${page} 页`
        : String(page || '').trim().replace(/^p\.(\d+)$/i, '第 $1 页');
    const linePart = line_start === line_end ? `第 ${line_start} 行` : `第 ${line_start}-${line_end} 行`;
    return pagePart ? `${pagePart} · ${linePart}` : linePart;
  }
  if (typeof page === 'number') return `第 ${page} 页`;
  const raw = String(page || '').trim();
  if (!raw) return '定位未知';
  if (/^p\.\d+$/i.test(raw)) return raw.replace(/^p\./i, '第 ') + ' 页';
  return raw;
}

export default function EvidenceCard({ source, index, onOpen, compact = false }: EvidenceCardProps) {
  const [expanded, setExpanded] = useState(false);
  const isAsset = Boolean(source.asset_id || source.thumbnail_url || source.caption);
  const label = isAsset ? '图表证据' : '文本证据';
  const summary = isAsset ? (source.summary || source.interpretation?.main_message || '') : '';
  const excerpt = source.excerpt || source.content || source.interpretation?.evidence_text || source.summary || '';
  const detailText = summary && excerpt === summary ? '' : excerpt;
  const locator = locatorLabel(source);
  const canExpand = detailText.length > 180 || detailText.includes('\n');

  return (
    <div
      className={`rounded-xl border bg-white p-3 text-left shadow-sm dark:bg-slate-800/80 ${
        source.is_primary
          ? 'border-blue-300 ring-1 ring-blue-100 dark:border-blue-700 dark:ring-blue-900/40'
          : 'border-slate-200 dark:border-slate-700'
      } ${
        compact ? '' : 'transition-colors hover:border-blue-300 dark:hover:border-blue-700'
      }`}
    >
      <div className="flex items-start gap-3">
        {isAsset ? (
          <div className="relative h-20 w-28 shrink-0 overflow-hidden rounded-lg border border-slate-200 bg-slate-100 dark:border-slate-700 dark:bg-slate-900">
            {source.thumbnail_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={source.thumbnail_url} alt={source.caption || source.ref_label || source.source} className="h-full w-full object-cover" />
            ) : (
              <div className="flex h-full w-full items-center justify-center text-slate-400">
                <ImageIcon size={20} />
              </div>
            )}
          </div>
        ) : null}

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            {index !== undefined ? (
              <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-blue-100 px-1.5 text-[11px] font-semibold text-blue-700 dark:bg-blue-900/30 dark:text-blue-200">
                {index}
              </span>
            ) : null}
            <div className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600 dark:bg-slate-700/60 dark:text-slate-200">
              {isAsset ? <BarChart3 size={12} /> : <BookOpen size={12} />}
              <span>{label}</span>
            </div>
            {source.is_primary ? (
              <div className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2 py-0.5 text-[11px] font-medium text-blue-700 dark:bg-blue-900/30 dark:text-blue-200">
                <Sparkles size={11} />
                <span>主证据</span>
              </div>
            ) : null}
            <div className="inline-flex items-center gap-1 rounded-full bg-slate-50 px-2 py-0.5 text-[11px] font-medium text-slate-500 dark:bg-slate-900/60 dark:text-slate-300">
              <MapPinned size={11} />
              <span>{locator}</span>
            </div>
            {source.source ? (
              <div className="inline-flex max-w-[200px] items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-300" title={cleanEvidenceTitle(source.source)}>
                <FileText size={11} />
                <span className="truncate">{cleanEvidenceTitle(source.source)}</span>
              </div>
            ) : null}
          </div>

          {summary ? (
            <div className="mt-3">
              <div className="mb-1 text-[11px] font-medium uppercase tracking-[0.18em] text-slate-400 dark:text-slate-500">结论</div>
              <div className="rounded-lg bg-slate-50 px-3 py-2 text-[13px] leading-6 whitespace-pre-line text-slate-700 dark:bg-slate-900/60 dark:text-slate-200">
                {summary}
              </div>
            </div>
          ) : null}

          {isAsset && detailText ? (
            <div className="mt-3">
              <div className="mb-1 text-[11px] font-medium uppercase tracking-[0.18em] text-slate-400 dark:text-slate-500">
                原文依据
              </div>
              <div
                className={`rounded-lg border border-slate-200 bg-white px-3 py-2 text-[12px] leading-6 whitespace-pre-line text-slate-600 dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-300 ${
                  expanded ? '' : 'line-clamp-4'
                }`}
              >
                {detailText}
              </div>
              {canExpand ? (
                <button
                  type="button"
                  onClick={() => setExpanded((prev) => !prev)}
                  className="mt-2 inline-flex items-center gap-1 text-[12px] font-medium text-slate-500 hover:text-blue-600 dark:text-slate-400 dark:hover:text-blue-300"
                >
                  {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  {expanded ? '收起' : '展开'}
                </button>
              ) : null}
            </div>
          ) : null}

          {onOpen ? (
            <button
              type="button"
              onClick={() => onOpen(source)}
              className="mt-3 inline-flex items-center gap-1 rounded-md border border-slate-200 px-2.5 py-1 text-[12px] font-medium text-blue-600 hover:border-blue-300 hover:bg-blue-50 dark:border-slate-700 dark:text-blue-300 dark:hover:border-blue-700 dark:hover:bg-blue-900/20"
            >
              查看原文
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
