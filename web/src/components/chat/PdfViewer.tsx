'use client';

import { useState, useEffect } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import { ChevronLeft, ChevronRight, X, ZoomIn, ZoomOut, Maximize2, Loader2 } from 'lucide-react';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';

// Configure pdf.js worker
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

interface PdfViewerProps {
    fileUrl: string | null;
    fileName?: string;
    initialPage?: number;
    onClose: () => void;
}

export default function PdfViewer({ fileUrl, fileName, initialPage = 1, onClose }: PdfViewerProps) {
    const [numPages, setNumPages] = useState<number>(0);
    const [pageNumber, setPageNumber] = useState<number>(initialPage);
    const [scale, setScale] = useState<number>(1.0);
    const [isLoading, setIsLoading] = useState(false);
    const [isFullscreen, setIsFullscreen] = useState(false);

    // Sync pageNumber when initialPage prop changes (e.g., user clicked a citation)
    useEffect(() => {
        if (initialPage && numPages && initialPage <= numPages) {
            setPageNumber(initialPage);
        }
    }, [initialPage, numPages]);

    // Reset state on new file
    useEffect(() => {
        setIsLoading(true);
        setPageNumber(initialPage || 1);
        setScale(1.0);
    }, [fileUrl]);

    if (!fileUrl) return null;

    function onDocumentLoadSuccess({ numPages }: { numPages: number }) {
        setNumPages(numPages);
        setIsLoading(false);
    }

    const zoomIn = () => setScale(s => Math.min(s + 0.2, 3));
    const zoomOut = () => setScale(s => Math.max(s - 0.2, 0.5));

    const prevPage = () => setPageNumber(p => Math.max(p - 1, 1));
    const nextPage = () => setPageNumber(p => Math.min(p + 1, numPages));

    return (
        <div className={`flex flex-col bg-slate-100 dark:bg-slate-900 border-l border-slate-200 dark:border-slate-700 h-full ${isFullscreen ? 'fixed inset-0 z-50' : 'w-[500px] shrink-0'}`}>
            {/* Header Toolbar */}
            <div className="h-14 px-4 flex items-center justify-between bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 shrink-0">
                <div className="flex items-center gap-3 overflow-hidden">
                    <button onClick={onClose} className="p-1.5 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg text-slate-500 transition-colors">
                        <X size={18} />
                    </button>
                    <span className="font-medium text-sm text-slate-700 dark:text-slate-200 truncate" title={fileName}>
                        {fileName || 'PDF Document'}
                    </span>
                </div>

                <div className="flex items-center gap-1">
                    {/* Zoom Controls */}
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

            {/* Pagination Toolbar */}
            <div className="h-10 px-4 flex items-center justify-center gap-4 bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 shrink-0 text-sm">
                <button
                    onClick={prevPage}
                    disabled={pageNumber <= 1}
                    className="p-1 hover:bg-slate-100 dark:hover:bg-slate-700 rounded disabled:opacity-30 text-slate-600 dark:text-slate-300"
                >
                    <ChevronLeft size={18} />
                </button>

                <span className="text-slate-600 dark:text-slate-300 tabular-nums">
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
                        <Page
                            pageNumber={pageNumber}
                            scale={scale}
                            loading={null}
                            className="bg-white"
                        />
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
