'use client';

import { useState, useEffect } from 'react';
import { Settings, Loader2, CheckCircle, AlertCircle, RefreshCw, Eye, EyeOff } from 'lucide-react';

interface LLMConfig {
    provider: string;
    base_url: string;
    model: string;
    api_key: string;
}

const PRESETS: { label: string; config: Partial<LLMConfig> }[] = [
    {
        label: 'Ollama (本地)',
        config: { provider: 'ollama', base_url: 'http://localhost:11434/v1', model: 'qwen3:0.6b', api_key: 'ollama' },
    },
    {
        label: 'OpenAI',
        config: { provider: 'openai', base_url: 'https://api.openai.com/v1', model: 'gpt-4o-mini', api_key: '' },
    },
    {
        label: 'DeepSeek',
        config: { provider: 'openai', base_url: 'https://api.deepseek.com/v1', model: 'deepseek-chat', api_key: '' },
    },
    {
        label: '硅基流动 (SiliconFlow)',
        config: { provider: 'openai', base_url: 'https://api.siliconflow.cn/v1', model: 'deepseek-ai/DeepSeek-V3', api_key: '' },
    },
    {
        label: '阿里云百炼 (DashScope)',
        config: { provider: 'openai', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus', api_key: '' },
    },
];

export default function SettingsPage() {
    const [config, setConfig] = useState<LLMConfig>({
        provider: '', base_url: '', model: '', api_key: '',
    });
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [testing, setTesting] = useState(false);
    const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
    const [saveResult, setSaveResult] = useState<{ success: boolean; message: string } | null>(null);
    const [showKey, setShowKey] = useState(false);

    useEffect(() => {
        fetchConfig();
    }, []);

    const fetchConfig = async () => {
        try {
            const res = await fetch('/api/settings/llm');
            const data = await res.json();
            if (data.success) {
                setConfig(data.data);
            }
        } catch (e) {
            console.error('Failed to fetch LLM config:', e);
        }
        setLoading(false);
    };

    const handleSave = async () => {
        setSaving(true);
        setSaveResult(null);
        setTestResult(null);
        try {
            const res = await fetch('/api/settings/llm', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config),
            });
            const data = await res.json();
            if (data.success) {
                setSaveResult({
                    success: true,
                    message: '✅ 配置已保存并立即生效，所有模块（对话/研究/写作）将使用新配置',
                });
                // Re-fetch to confirm persistence
                await fetchConfig();
            } else {
                setSaveResult({ success: false, message: `保存失败: ${data.detail || '未知错误'}` });
            }
        } catch (e) {
            setSaveResult({ success: false, message: `保存失败: ${e}` });
        }
        setSaving(false);
    };

    const handleTest = async () => {
        setTesting(true);
        setTestResult(null);
        try {
            // Test with current form values (even before saving)
            const res = await fetch('/api/settings/llm/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config),
            });
            const data = await res.json();
            setTestResult({
                success: data.success,
                message: data.success
                    ? `✅ 连接成功！模型: ${data.data?.model} | 回复: "${data.data?.response}"`
                    : `❌ 连接失败: ${data.error}`,
            });
        } catch (e) {
            setTestResult({ success: false, message: `连接失败: ${e}` });
        }
        setTesting(false);
    };

    const applyPreset = (preset: Partial<LLMConfig>) => {
        // Keep existing api_key if the preset doesn't provide one
        const newConfig = { ...config, ...preset };
        if (!preset.api_key && config.api_key) {
            newConfig.api_key = config.api_key;
        }
        setConfig(newConfig);
        setSaveResult(null);
        setTestResult(null);
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center h-full">
                <Loader2 className="animate-spin text-slate-400" size={32} />
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-slate-50 dark:bg-slate-900 p-8 transition-colors">
            <div className="max-w-2xl mx-auto">
                {/* Header */}
                <div className="mb-8">
                    <h1 className="text-2xl font-bold text-slate-800 dark:text-white mb-2 flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-slate-600 to-slate-500 flex items-center justify-center text-white shadow-lg">
                            <Settings size={20} />
                        </div>
                        系统设置
                    </h1>
                    <p className="text-slate-500 dark:text-slate-400">
                        配置 LLM 模型和 API 连接，保存后全局生效
                    </p>
                </div>

                {/* LLM Configuration */}
                <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-6 shadow-sm">
                    <h2 className="text-lg font-semibold text-slate-800 dark:text-white mb-1">
                        🤖 LLM 配置
                    </h2>
                    <p className="text-xs text-slate-400 dark:text-slate-500 mb-4">
                        保存后对话、研究、写作等所有模块立即切换到新配置，重启后依然保留
                    </p>

                    {/* Presets */}
                    <div className="mb-6">
                        <label className="block text-sm font-medium text-slate-600 dark:text-slate-300 mb-2">
                            快速预设
                        </label>
                        <div className="flex flex-wrap gap-2">
                            {PRESETS.map((p) => (
                                <button
                                    key={p.label}
                                    onClick={() => applyPreset(p.config)}
                                    className={`px-3 py-1.5 rounded-lg text-sm border transition-all ${config.base_url === p.config.base_url
                                            ? 'bg-blue-50 dark:bg-blue-900/30 border-blue-300 dark:border-blue-700 text-blue-700 dark:text-blue-300 font-medium'
                                            : 'bg-slate-50 dark:bg-slate-700 border-slate-200 dark:border-slate-600 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-600'
                                        }`}
                                >
                                    {p.label}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Form Fields */}
                    <div className="space-y-4">
                        <div>
                            <label className="block text-sm font-medium text-slate-600 dark:text-slate-300 mb-1">
                                Provider
                            </label>
                            <input
                                value={config.provider}
                                onChange={(e) => setConfig({ ...config, provider: e.target.value })}
                                className="w-full px-4 py-2.5 rounded-lg border border-slate-200 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                                placeholder="ollama / openai"
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-slate-600 dark:text-slate-300 mb-1">
                                Base URL
                            </label>
                            <input
                                value={config.base_url}
                                onChange={(e) => setConfig({ ...config, base_url: e.target.value })}
                                className="w-full px-4 py-2.5 rounded-lg border border-slate-200 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm font-mono"
                                placeholder="http://localhost:11434/v1"
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-slate-600 dark:text-slate-300 mb-1">
                                Model
                            </label>
                            <input
                                value={config.model}
                                onChange={(e) => setConfig({ ...config, model: e.target.value })}
                                className="w-full px-4 py-2.5 rounded-lg border border-slate-200 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm font-mono"
                                placeholder="qwen3:0.6b"
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-slate-600 dark:text-slate-300 mb-1">
                                API Key
                            </label>
                            <div className="relative">
                                <input
                                    type={showKey ? 'text' : 'password'}
                                    value={config.api_key}
                                    onChange={(e) => setConfig({ ...config, api_key: e.target.value })}
                                    className="w-full px-4 py-2.5 pr-10 rounded-lg border border-slate-200 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm font-mono"
                                    placeholder="sk-..."
                                />
                                <button
                                    onClick={() => setShowKey(!showKey)}
                                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
                                >
                                    {showKey ? <EyeOff size={16} /> : <Eye size={16} />}
                                </button>
                            </div>
                        </div>
                    </div>

                    {/* Actions */}
                    <div className="mt-6 flex items-center gap-3">
                        <button
                            onClick={handleSave}
                            disabled={saving}
                            className="px-5 py-2.5 bg-blue-500 text-white rounded-lg font-medium hover:bg-blue-600 disabled:opacity-50 transition-colors flex items-center gap-2 text-sm"
                        >
                            {saving ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle size={16} />}
                            保存配置
                        </button>
                        <button
                            onClick={handleTest}
                            disabled={testing}
                            className="px-5 py-2.5 bg-emerald-500 text-white rounded-lg font-medium hover:bg-emerald-600 disabled:opacity-50 transition-colors flex items-center gap-2 text-sm"
                        >
                            {testing ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
                            测试连接
                        </button>
                    </div>

                    {/* Results */}
                    {saveResult && (
                        <div className={`mt-4 p-3 rounded-lg text-sm flex items-start gap-2 ${saveResult.success
                                ? 'bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300'
                                : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300'
                            }`}>
                            {saveResult.success ? <CheckCircle size={16} className="mt-0.5 shrink-0" /> : <AlertCircle size={16} className="mt-0.5 shrink-0" />}
                            {saveResult.message}
                        </div>
                    )}
                    {testResult && (
                        <div className={`mt-3 p-3 rounded-lg text-sm flex items-start gap-2 ${testResult.success
                                ? 'bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-300'
                                : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300'
                            }`}>
                            {testResult.success ? <CheckCircle size={16} className="mt-0.5 shrink-0" /> : <AlertCircle size={16} className="mt-0.5 shrink-0" />}
                            {testResult.message}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
