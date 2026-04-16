'use client';

import { useState, useRef, useCallback, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { AlertCircle, BookOpen, MapPinned } from 'lucide-react';
import type { EvidenceSource } from './evidence';
export type CitationSource = EvidenceSource;

interface CitationCardProps {
    index: number;
    source?: CitationSource;
    onClick?: () => void;
}

function locatorLabel(source: EvidenceSource) {
    const rawPage = source.page;
    if (source.line_start && source.line_end) {
        const pageText =
            typeof rawPage === 'number'
                ? `第 ${rawPage} 页`
                : String(rawPage || '').trim().replace(/^p\.(\d+)$/i, '第 $1 页');
        const lineText =
            source.line_start === source.line_end
                ? `第 ${source.line_start} 行`
                : `第 ${source.line_start}-${source.line_end} 行`;
        return pageText ? `${pageText} · ${lineText}` : lineText;
    }
    if (typeof rawPage === 'number') return `第 ${rawPage} 页`;
    const raw = String(rawPage || '').trim();
    if (!raw) return '定位未知';
    if (/^p\.\d+$/i.test(raw)) return raw.replace(/^p\./i, '第 ') + ' 页';
    return raw;
}

export default function CitationCard({ index, source, onClick }: CitationCardProps) {
    const [isHovered, setIsHovered] = useState(false);
    const [tooltipPos, setTooltipPos] = useState<{ top: number; left: number } | null>(null);
    const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
    const anchorRef = useRef<HTMLSpanElement | null>(null);
    const canUseDOM = typeof document !== 'undefined';

    useEffect(() => {
        return () => {
            if (hideTimer.current) {
                clearTimeout(hideTimer.current);
                hideTimer.current = null;
            }
        };
    }, []);

    const updateTooltipPos = useCallback(() => {
        const el = anchorRef.current;
        if (!el) return;
        const rect = el.getBoundingClientRect();
        setTooltipPos({
            top: rect.top - 8,
            left: rect.left + rect.width / 2,
        });
    }, []);

    const showCard = useCallback(() => {
        if (hideTimer.current) clearTimeout(hideTimer.current);
        updateTooltipPos();
        setIsHovered(true);
    }, [updateTooltipPos]);

    const hideCard = useCallback(() => {
        hideTimer.current = setTimeout(() => setIsHovered(false), 150);
    }, []);

    useEffect(() => {
        if (!isHovered) return;

        const onReflow = () => updateTooltipPos();
        window.addEventListener('scroll', onReflow, true);
        window.addEventListener('resize', onReflow);

        return () => {
            window.removeEventListener('scroll', onReflow, true);
            window.removeEventListener('resize', onReflow);
        };
    }, [isHovered, updateTooltipPos]);

    if (!source) {
        return (
            <span className="inline-flex items-center justify-center min-w-[1.25rem] h-5 px-1 rounded-full bg-slate-100 dark:bg-slate-700/50 text-slate-400 dark:text-slate-500 text-[10px] font-medium mx-0.5 align-super" title="暂无来源详情">
                {index}
            </span>
        );
    }

    const label = source.asset_id ? '图表证据' : '文本证据';
    const locator = locatorLabel(source);
    const preview = source.asset_id ? (source.summary || source.excerpt || source.content) : '';

    return (
        <span
            ref={anchorRef}
            className="inline-block mx-0.5 align-super"
            onMouseEnter={showCard}
            onMouseLeave={hideCard}
        >
            <button
                type="button"
                onClick={onClick}
                className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-blue-100 hover:bg-blue-200 dark:bg-blue-900/40 dark:hover:bg-blue-800/60 text-blue-600 dark:text-blue-400 text-[10px] font-semibold transition-colors shadow-sm cursor-pointer"
            >
                {index}
            </button>

            {canUseDOM && isHovered && tooltipPos
                ? createPortal(
                    <div
                        className="fixed w-72 -translate-x-1/2 -translate-y-full bg-white dark:bg-slate-800 rounded-xl shadow-xl border border-slate-200 dark:border-slate-700 p-3 z-[100] text-left cursor-default"
                        style={{ top: tooltipPos.top, left: tooltipPos.left }}
                        onMouseEnter={showCard}
                        onMouseLeave={hideCard}
                    >
                        <div className="flex items-start gap-2 mb-2">
                            <BookOpen size={14} className="text-blue-500 mt-0.5 shrink-0" />
                            <div className="flex-1 min-w-0">
                                <div className="text-sm font-semibold text-slate-800 dark:text-slate-200 truncate">
                                    {label}
                                </div>
                                <div className="mt-1 inline-flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400">
                                    <MapPinned size={12} />
                                    <span>{locator}</span>
                                </div>
                            </div>
                        </div>

                        {preview ? (
                            <div className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed line-clamp-4 bg-slate-50 dark:bg-slate-900/50 p-2 rounded-lg border border-slate-100 dark:border-slate-700/50">
                                &ldquo;{preview}&rdquo;
                            </div>
                        ) : source.asset_id ? (
                            <div className="flex items-center gap-1 text-xs text-amber-500 bg-amber-50 dark:bg-amber-900/20 p-2 rounded-lg">
                                <AlertCircle size={12} /> 无摘要内容
                            </div>
                        ) : null}

                        {source.thumbnail_url ? (
                            <div className="mt-2 overflow-hidden rounded-lg border border-slate-100 dark:border-slate-700/50">
                                {/* eslint-disable-next-line @next/next/no-img-element */}
                                <img
                                    src={source.thumbnail_url}
                                    alt={source.caption || source.ref_label || source.source}
                                    className="h-28 w-full object-cover"
                                />
                            </div>
                        ) : null}

                        {source.caption ? (
                            <div className="mt-2 text-[11px] leading-relaxed text-slate-500 dark:text-slate-400">
                                {source.ref_label ? `${source.ref_label} · ` : ''}{source.caption}
                            </div>
                        ) : null}

                        {source.interpretation?.main_message ? (
                            <div className="mt-2 text-[11px] leading-relaxed text-slate-600 dark:text-slate-300">
                                {source.interpretation.main_message}
                            </div>
                        ) : null}

                        <button
                            type="button"
                            onClick={onClick}
                            className="w-full text-[10px] text-center text-blue-500 hover:text-blue-700 mt-2 font-medium cursor-pointer"
                        >
                            点击查看原文
                        </button>
                    </div>,
                    document.body
                )
                : null}
        </span>
    );
}
