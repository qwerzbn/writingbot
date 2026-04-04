'use client';

import { useState, useEffect, useRef } from 'react';
import { Loader2, RefreshCw, AlertCircle } from 'lucide-react';

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
        <div className="h-screen w-full bg-slate-50 dark:bg-slate-900">
            <div className="relative h-full w-full">
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
                        className="h-full w-full border-0"
                        title="FastWrite - 协同写作"
                        allow="clipboard-read; clipboard-write"
                    />
                )}
            </div>
        </div>
    );
}
