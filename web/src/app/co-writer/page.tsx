'use client';

import { useEffect, useRef, useState } from 'react';
import { AlertCircle, Loader2, RefreshCw } from 'lucide-react';

const DEFAULT_FASTWRITE_URL = process.env.NEXT_PUBLIC_FASTWRITE_URL || 'http://127.0.0.1:3002';

interface FastWriteHealthResponse {
  success: boolean;
  data?: {
    available?: boolean;
    url?: string;
    error?: string;
    warning?: string;
  };
}

export default function CoWriterPage() {
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [fastWriteUrl, setFastWriteUrl] = useState(DEFAULT_FASTWRITE_URL);
  const [healthMessage, setHealthMessage] = useState('');
  const iframeRef = useRef<HTMLIFrameElement>(null);

  const checkConnection = async (cancelledRef?: { cancelled: boolean }) => {
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 5000);
      const response = await fetch('/api/fastwrite/health', {
        method: 'GET',
        cache: 'no-store',
        signal: controller.signal,
      });
      clearTimeout(timeout);

      const payload = (await response.json()) as FastWriteHealthResponse;
      if (cancelledRef?.cancelled) return;

      if (payload?.data?.available) {
        setFastWriteUrl(payload.data.url || DEFAULT_FASTWRITE_URL);
        setHealthMessage(payload.data.warning || '');
        setStatus('ready');
        return;
      }

      setHealthMessage(payload?.data?.error || 'FastWrite service is unavailable.');
      setStatus('error');
    } catch (error) {
      if (cancelledRef?.cancelled) return;
      setHealthMessage(error instanceof Error ? error.message : 'FastWrite health check failed.');
      setStatus('error');
    }
  };

  useEffect(() => {
    const cancelledRef = { cancelled: false };
    void checkConnection(cancelledRef);
    return () => {
      cancelledRef.cancelled = true;
    };
  }, []);

  const handleRetry = () => {
    setStatus('loading');
    void checkConnection();
  };

  return (
    <div className="h-screen w-full bg-slate-50 dark:bg-slate-900">
      <div className="relative h-full w-full">
        {status === 'loading' && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-slate-50 dark:bg-slate-900">
            <Loader2 size={32} className="mb-4 animate-spin text-rose-500" />
            <p className="text-sm text-slate-500 dark:text-slate-400">Checking FastWrite availability...</p>
          </div>
        )}

        {status === 'error' && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-slate-50 dark:bg-slate-900 px-6">
            <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-red-50 dark:bg-red-900/20">
              <AlertCircle size={32} className="text-red-400" />
            </div>
            <h3 className="mb-2 text-lg font-semibold text-slate-700 dark:text-slate-200">FastWrite unavailable</h3>
            <p className="mb-6 max-w-xl text-center text-sm text-slate-500 dark:text-slate-400">
              Co-writer is running in degraded mode. Start FastWrite and retry. Use{' '}
              <code className="rounded bg-slate-200 px-1.5 py-0.5 text-xs dark:bg-slate-700">start_dev.sh</code> or{' '}
              <code className="rounded bg-slate-200 px-1.5 py-0.5 text-xs dark:bg-slate-700">start_dev.ps1</code>.
              {healthMessage ? ` (${healthMessage})` : ''}
            </p>
            <button
              onClick={handleRetry}
              className="flex items-center gap-2 rounded-lg bg-rose-500 px-4 py-2 text-sm text-white transition-colors hover:bg-rose-600"
              type="button"
            >
              <RefreshCw size={14} />
              Retry
            </button>
          </div>
        )}

        {status === 'ready' && (
          <iframe
            ref={iframeRef}
            src={fastWriteUrl}
            className="h-full w-full border-0"
            title="FastWrite co-writer"
            allow="clipboard-read; clipboard-write"
          />
        )}
      </div>
    </div>
  );
}
