'use client';

import { useState, useEffect } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import { ChevronLeft, ChevronRight, X, ZoomIn, ZoomOut, Maximize2, Loader2 } from 'lucide-react';

import type { EvidenceHighlight } from './evidence';

// Configure pdf.js worker
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

interface PdfViewerProps {
    fileUrl: string | null;
    initialPage?: number;
    highlightBoxes?: EvidenceHighlight[];
    onClose: () => void;
}

export default function PdfViewer({ fileUrl, initialPage = 1, highlightBoxes = [], onClose }: PdfViewerProps) {
    const [numPages, setNumPages] = useState<number>(0);
    const [pageNumber, setPageNumber] = useState<number>(initialPage);
    const [scale, setScale] = useState<number>(1.0);
    const [isLoading, setIsLoading] = useState(false);
    const [isFullscreen, setIsFullscreen] = useState(false);
    const [pageBaseSize, setPageBaseSize] = useState<{ width: number; height: number } | null>(null);
    const [pageViewport, setPageViewport] = useState<{ width: number; height: number } | null>(null);

    // Sync pageNumber when initialPage prop changes (e.g., user clicked a citation)
    useEffect(() => {
        if (initialPage && numPages && initialPage <= numPages) {
            // eslint-disable-next-line react-hooks/set-state-in-effect
            setPageNumber(initialPage);
        }
    }, [initialPage, numPages]);

    // Reset state on new file
    useEffect(() => {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setIsLoading(true);
        setPageNumber(initialPage || 1);
        setScale(1.0);
        setPageBaseSize(null);
        setPageViewport(null);
    }, [fileUrl, initialPage]);

    useEffect(() => {
        if (!pageBaseSize) return;
        setPageViewport({
            width: pageBaseSize.width * scale,
            height: pageBaseSize.height * scale,
        });
    }, [pageBaseSize, scale]);

    if (!fileUrl) return null;

    function onDocumentLoadSuccess({ numPages }: { numPages: number }) {
        setNumPages(numPages);
        setIsLoading(false);
    }

    const zoomIn = () => setScale(s => Math.min(s + 0.2, 3));
    const zoomOut = () => setScale(s => Math.max(s - 0.2, 0.5));

    const prevPage = () => setPageNumber(p => Math.max(p - 1, 1));
    const nextPage = () => setPageNumber(p => Math.min(p + 1, numPages));

    const currentHighlights = highlightBoxes.filter((box) => {
        const boxPage = typeof box.page === 'number' ? box.page : Number(String(box.page || '').match(/\d+/)?.[0] || 0);
        return boxPage === pageNumber && Array.isArray(box.bbox) && box.bbox.length === 4 && box.page_width && box.page_height;
    });

    return (
        <div className={`flex flex-col bg-slate-100 dark:bg-slate-900 border-l border-slate-200 dark:border-slate-700 h-full ${isFullscreen ? 'fixed inset-0 z-50' : 'w-[500px] shrink-0'}`}>
            <div className="border-b border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shrink-0">
                <div className="grid h-14 grid-cols-[auto_1fr_auto] items-center gap-3 px-4">
                    <div className="flex items-center">
                        <button onClick={onClose} className="p-1.5 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg text-slate-500 transition-colors" aria-label="关闭 PDF 预览">
                            <X size={18} />
                        </button>
                    </div>

                    <div className="flex items-center justify-center gap-3 text-sm">
                        <button
                            onClick={prevPage}
                            disabled={pageNumber <= 1}
                            className="p-1 hover:bg-slate-100 dark:hover:bg-slate-700 rounded disabled:opacity-30 text-slate-600 dark:text-slate-300"
                        >
                            <ChevronLeft size={18} />
                        </button>

                        <span className="text-slate-600 dark:text-slate-300 tabular-nums whitespace-nowrap">
                            第 <input
                                type="number"
                                value={pageNumber}
                                onChange={(e) => {
                                    const val = parseInt(e.target.value);
                                    if (val >= 1 && val <= numPages) setPageNumber(val);
                                }}
                                className="w-12 text-center bg-slate-100 dark:bg-slate-700 border-none rounded py-0.5 mx-1 outline-none focus:ring-1 focus:ring-blue-500"
                            /> 页 / 共 {numPages || '-'} 页
                        </span>

                        <button
                            onClick={nextPage}
                            disabled={pageNumber >= numPages}
                            className="p-1 hover:bg-slate-100 dark:hover:bg-slate-700 rounded disabled:opacity-30 text-slate-600 dark:text-slate-300"
                        >
                            <ChevronRight size={18} />
                        </button>
                    </div>

                    <div className="flex items-center gap-1 justify-self-end">
                        <div className="flex items-center bg-slate-100 dark:bg-slate-700 rounded-lg p-0.5 mr-2">
                            <button onClick={zoomOut} className="p-1.5 hover:bg-white dark:hover:bg-slate-600 rounded text-slate-600 dark:text-slate-300">
                                <ZoomOut size={16} />
                            </button>
                            <span className="text-xs font-medium w-12 text-center text-slate-600 dark:text-slate-300">
                                {Math.round(scale * 100)}%
                            </span>
                            <button onClick={zoomIn} className="p-1.5 hover:bg-white dark:hover:bg-slate-600 rounded text-slate-600 dark:text-slate-300">
                                <ZoomIn size={16} />
                            </button>
                        </div>

                        <button
                            onClick={() => setIsFullscreen(!isFullscreen)}
                            className="p-1.5 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg text-slate-500 transition-colors"
                            title={isFullscreen ? '退出全屏' : '全屏预览'}
                        >
                            <Maximize2 size={16} />
                        </button>
                    </div>
                </div>
            </div>

            {/* Document Container */}
            <div className="flex-1 overflow-auto bg-slate-200 dark:bg-slate-900/50 p-4 flex justify-center custom-scrollbar relative">
                {isLoading && (
                    <div className="absolute inset-0 flex items-center justify-center flex-col gap-3 text-slate-500 z-10">
                        <Loader2 className="animate-spin" size={32} />
                        <span className="text-sm">加载文档中...</span>
                    </div>
                )}
                <div className="shadow-xl bg-white transition-transform origin-top min-w-min">
                    <Document
                        file={fileUrl}
                        onLoadSuccess={onDocumentLoadSuccess}
                        loading={null}
                        error={<div className="p-8 text-red-500">无法加载 PDF 文档</div>}
                    >
                        <div
                            className="relative"
                            style={pageViewport ? { width: `${pageViewport.width}px`, height: `${pageViewport.height}px` } : undefined}
                        >
                            <Page
                                pageNumber={pageNumber}
                                scale={scale}
                                loading={null}
                                className="bg-white"
                                onLoadSuccess={(page) => {
                                    const viewport = page.getViewport({ scale: 1 });
                                    setPageBaseSize({ width: viewport.width, height: viewport.height });
                                    setIsLoading(false);
                                }}
                                onRenderSuccess={() => setIsLoading(false)}
                            />
                            {pageViewport ? (
                                <div className="pointer-events-none absolute inset-0">
                                    {currentHighlights.map((box, index) => {
                                        const [x0, y0, x1, y1] = (box.bbox || []).map((value) => Number(value));
                                        const widthRatio = pageViewport.width / Number(box.page_width || 1);
                                        const heightRatio = pageViewport.height / Number(box.page_height || 1);
                                        const left = x0 * widthRatio;
                                        const top = y0 * heightRatio;
                                        const width = Math.max(8, (x1 - x0) * widthRatio);
                                        const height = Math.max(8, (y1 - y0) * heightRatio);
                                        return (
                                            <div
                                                key={`${pageNumber}:${index}:${left}:${top}`}
                                                className="absolute rounded-sm border-2 border-amber-400 shadow-[0_0_0_1px_rgba(251,191,36,0.4)]"
                                                style={{ left, top, width, height }}
                                            />
                                        );
                                    })}
                                </div>
                            ) : null}
                        </div>
                    </Document>
                </div>
            </div>

            <style jsx global>{`
                .custom-scrollbar::-webkit-scrollbar {
                    width: 8px;
                    height: 8px;
                }
                .custom-scrollbar::-webkit-scrollbar-track {
                    background: transparent;
                }
                .custom-scrollbar::-webkit-scrollbar-thumb {
                    background-color: #cbd5e1;
                    border-radius: 4px;
                }
                .dark .custom-scrollbar::-webkit-scrollbar-thumb {
                    background-color: #475569;
                }
            `}</style>
        </div>
    );
}
