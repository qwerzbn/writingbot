'use client';

import { useState, useEffect, useRef } from 'react';
import { PenTool, Loader2, RefreshCw, ExternalLink, AlertCircle } from 'lucide-react';

const FASTWRITE_URL = 'http://localhost:3002';

export default function CoWriterPage() {
    const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
    const iframeRef = useRef<HTMLIFrameElement>(null);

    // Check if FastWrite is available
    useEffect(() => {
        let cancelled = false;

        const checkConnection = async () => {
            try {
                // Use a simple fetch to check if the dev server responds
                const controller = new AbortController();
                const timeout = setTimeout(() => controller.abort(), 5000);

                await fetch(FASTWRITE_URL, {
                    mode: 'no-cors',
                    signal: controller.signal,
                });
                clearTimeout(timeout);

                if (!cancelled) setStatus('ready');
            } catch {
                if (!cancelled) setStatus('error');
            }
        };

        checkConnection();
        return () => { cancelled = true; };
    }, []);

    const handleRetry = () => {
        setStatus('loading');
        // Re-trigger the connection check
        const checkConnection = async () => {
            try {
                const controller = new AbortController();
                const timeout = setTimeout(() => controller.abort(), 5000);
                await fetch(FASTWRITE_URL, { mode: 'no-cors', signal: controller.signal });
                clearTimeout(timeout);
                setStatus('ready');
            } catch {
                setStatus('error');
            }
        };
        checkConnection();
    };

    return (
        <div className="h-screen w-full flex flex-col bg-slate-50 dark:bg-slate-900">
            {/* Minimal header bar */}
            <div className="h-10 px-4 flex items-center justify-between bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 shrink-0">
                <div className="flex items-center gap-2">
                    <div className="w-6 h-6 rounded-md bg-gradient-to-br from-rose-500 to-pink-400 flex items-center justify-center text-white">
                        <PenTool size={13} />
                    </div>
                    <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
                        协同写作
                    </span>
                    <span className="text-xs text-slate-400 dark:text-slate-500">FastWrite</span>
                </div>
                <a
                    href={FASTWRITE_URL}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 flex items-center gap-1 transition-colors"
                    title="在新窗口中打开"
                >
                    <ExternalLink size={12} />
                </a>
            </div>

            {/* Content area */}
            <div className="flex-1 relative">
                {/* Loading state */}
                {status === 'loading' && (
                    <div className="absolute inset-0 flex flex-col items-center justify-center bg-slate-50 dark:bg-slate-900 z-10">
                        <Loader2 size={32} className="animate-spin text-rose-500 mb-4" />
                        <p className="text-sm text-slate-500 dark:text-slate-400">
                            正在连接 FastWrite 服务...
                        </p>
                    </div>
                )}

                {/* Error state */}
                {status === 'error' && (
                    <div className="absolute inset-0 flex flex-col items-center justify-center bg-slate-50 dark:bg-slate-900 z-10">
                        <div className="w-16 h-16 rounded-2xl bg-red-50 dark:bg-red-900/20 flex items-center justify-center mb-4">
                            <AlertCircle size={32} className="text-red-400" />
                        </div>
                        <h3 className="text-lg font-semibold text-slate-700 dark:text-slate-200 mb-2">
                            无法连接 FastWrite
                        </h3>
                        <p className="text-sm text-slate-500 dark:text-slate-400 mb-6 text-center max-w-md">
                            请确保 FastWrite 服务已启动。通过 <code className="px-1.5 py-0.5 bg-slate-200 dark:bg-slate-700 rounded text-xs">start_dev.sh</code> 脚本可以同时启动所有服务。
                        </p>
                        <button
                            onClick={handleRetry}
                            className="px-4 py-2 bg-rose-500 hover:bg-rose-600 text-white text-sm rounded-lg flex items-center gap-2 transition-colors"
                        >
                            <RefreshCw size={14} />
                            重试连接
                        </button>
                    </div>
                )}

                {/* iframe - always mounted when ready */}
                {status === 'ready' && (
                    <iframe
                        ref={iframeRef}
                        src={FASTWRITE_URL}
                        className="w-full h-full border-0"
                        title="FastWrite - 协同写作"
                        allow="clipboard-read; clipboard-write"
                    />
                )}
            </div>
        </div>
    );
}
