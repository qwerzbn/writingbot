import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { AlertCircle, Bot, ExternalLink, Loader2, RefreshCw, Server, ShieldCheck, X } from 'lucide-react';

import type { GlobalLLMConfig } from '../types';

interface LLMSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

type ModalState =
  | { status: 'idle' | 'loading' }
  | { status: 'ready'; config: GlobalLLMConfig & { source?: string; has_api_key?: boolean } }
  | { status: 'error'; message: string };

const MAIN_SETTINGS_URL = 'http://localhost:3000/settings';

const LLMSettingsModal: React.FC<LLMSettingsModalProps> = ({ isOpen, onClose }) => {
  const [state, setState] = useState<ModalState>({ status: 'idle' });
  const [testMessage, setTestMessage] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);

  const loadConfig = async () => {
    setState({ status: 'loading' });
    setTestMessage(null);
    try {
      const response = await fetch('/api/llm-config');
      const data = await response.json() as (GlobalLLMConfig & { error?: string; source?: string; has_api_key?: boolean });
      if (!response.ok || data.error) {
        throw new Error(data.error || `Failed to load settings (${response.status})`);
      }
      setState({ status: 'ready', config: data });
    } catch (error) {
      setState({
        status: 'error',
        message: error instanceof Error ? error.message : 'Failed to load global AI settings',
      });
    }
  };

  useEffect(() => {
    if (!isOpen) return;
    loadConfig();
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isOpen, onClose]);

  const handleTest = async () => {
    setTesting(true);
    setTestMessage(null);
    try {
      const response = await fetch('/api/llm-config/test', { method: 'POST' });
      const data = await response.json() as { success?: boolean; error?: string; data?: { model?: string; response?: string }; model?: string; message?: string };
      if (!data.success) {
        throw new Error(data.error || 'Connection test failed');
      }
      const resultModel = data.data?.model || data.model;
      const resultResponse = data.data?.response || data.message || 'OK';
      setTestMessage(`连接正常。模型: ${resultModel} | 响应: ${resultResponse}`);
    } catch (error) {
      setTestMessage(error instanceof Error ? error.message : 'Connection test failed');
    } finally {
      setTesting(false);
    }
  };

  if (!isOpen) return null;

  return createPortal(
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/40 backdrop-blur-sm p-6">
      <div className="w-full max-w-xl rounded-2xl border border-slate-200 bg-white shadow-2xl overflow-hidden">
        <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-100 text-blue-600">
              <Bot size={20} />
            </div>
            <div>
              <h3 className="text-base font-semibold text-slate-800">全局 AI 设置</h3>
              <p className="text-xs text-slate-500">FastWrite 现在直接使用 WritingBot 主站中的统一模型配置。</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-slate-200 hover:text-slate-700"
            title="关闭"
          >
            <X size={18} />
          </button>
        </div>

        <div className="space-y-4 px-5 py-5">
          {state.status === 'loading' && (
            <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-5 text-sm text-slate-600">
              <Loader2 size={18} className="animate-spin" />
              正在读取主站 AI 设置...
            </div>
          )}

          {state.status === 'error' && (
            <div className="rounded-xl border border-red-200 bg-red-50 p-4">
              <div className="mb-2 flex items-center gap-2 text-sm font-medium text-red-700">
                <AlertCircle size={16} />
                无法连接 WritingBot 主站设置
              </div>
              <p className="text-sm text-red-600">{state.message}</p>
              <p className="mt-3 text-xs text-red-500">
                AI 写作功能依赖主站 `http://localhost:5001/api/settings/llm`。请先启动主站服务，再返回此处刷新。
              </p>
            </div>
          )}

          {state.status === 'ready' && (
            <div className="grid gap-3">
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                <div className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-700">
                  <ShieldCheck size={16} />
                  当前生效配置
                </div>
                <div className="grid gap-3 text-sm">
                  <div>
                    <div className="mb-1 text-xs uppercase tracking-wide text-slate-400">Provider</div>
                    <div className="font-medium text-slate-800">{state.config.provider || '未设置'}</div>
                  </div>
                  <div>
                    <div className="mb-1 text-xs uppercase tracking-wide text-slate-400">Base URL</div>
                    <div className="break-all font-medium text-slate-800">{state.config.base_url || '未设置'}</div>
                  </div>
                  <div>
                    <div className="mb-1 text-xs uppercase tracking-wide text-slate-400">Model</div>
                    <div className="font-medium text-slate-800">{state.config.model || '未设置'}</div>
                  </div>
                  <div>
                    <div className="mb-1 text-xs uppercase tracking-wide text-slate-400">API Key</div>
                    <div className="font-mono text-slate-700">{state.config.api_key || '未设置'}</div>
                  </div>
                </div>
              </div>

              <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
                FastWrite 不再维护独立 AI 配置。要修改模型、地址或密钥，请直接打开主站设置页。
              </div>
            </div>
          )}

          {testMessage && (
            <div className={`rounded-xl border p-3 text-sm ${
              testMessage.includes('连接正常')
                ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                : 'border-red-200 bg-red-50 text-red-700'
            }`}>
              {testMessage}
            </div>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-slate-200 bg-slate-50 px-5 py-4">
          <button
            onClick={loadConfig}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-100"
          >
            <RefreshCw size={14} />
            刷新
          </button>

          <div className="flex items-center gap-2">
            <button
              onClick={handleTest}
              disabled={state.status !== 'ready' || testing}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {testing ? <Loader2 size={14} className="animate-spin" /> : <Server size={14} />}
              测试当前配置
            </button>
            <a
              href={MAIN_SETTINGS_URL}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700"
            >
              打开主站设置
              <ExternalLink size={14} />
            </a>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
};

export default LLMSettingsModal;
