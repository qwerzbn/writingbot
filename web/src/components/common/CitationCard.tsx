'use client';

import { useState, useRef, useCallback, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { BookOpen, AlertCircle } from 'lucide-react';

export interface CitationSource {
    source: string;
    page: number | string;
    content?: string;
    score?: number;
    file_id?: string;
}

interface CitationCardProps {
    index: number;
    source?: CitationSource;
    onClick?: () => void;
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
                                <div className="text-sm font-semibold text-slate-800 dark:text-slate-200 truncate" title={source.source}>
                                    {source.source}
                                </div>
                                <div className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                                    第 {source.page} 页
                                    {source.score !== undefined && ` · 相关度: ${(source.score * 100).toFixed(1)}%`}
                                </div>
                            </div>
                        </div>

                        {source.content ? (
                            <div className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed line-clamp-4 bg-slate-50 dark:bg-slate-900/50 p-2 rounded-lg border border-slate-100 dark:border-slate-700/50">
                                &ldquo;{source.content}...&rdquo;
                            </div>
                        ) : (
                            <div className="flex items-center gap-1 text-xs text-amber-500 bg-amber-50 dark:bg-amber-900/20 p-2 rounded-lg">
                                <AlertCircle size={12} /> 无摘要内容
                            </div>
                        )}

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
