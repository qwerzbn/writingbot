'use client';

import { useState } from 'react';
import { PenTool, Loader2, Copy, Check, RefreshCw, Minimize2, Maximize2, Sparkles } from 'lucide-react';

const API_BASE = 'http://localhost:5001';

const actions = [
    { key: 'rewrite', label: '改写', icon: RefreshCw, desc: '重新表述，保持原意' },
    { key: 'expand', label: '扩展', icon: Maximize2, desc: '补充更多细节和论据' },
    { key: 'shorten', label: '精简', icon: Minimize2, desc: '去除冗余，保留核心' },
    { key: 'polish', label: '润色', icon: Sparkles, desc: '提升文采和可读性' },
];

export default function CoWriterPage() {
    const [inputText, setInputText] = useState('');
    const [instruction, setInstruction] = useState('');
    const [action, setAction] = useState('rewrite');
    const [result, setResult] = useState('');
    const [loading, setLoading] = useState(false);
    const [copied, setCopied] = useState(false);

    const handleEdit = async () => {
        if (!inputText.trim() || loading) return;
        setLoading(true);
        setResult('');

        try {
            const res = await fetch(`${API_BASE}/api/co-writer/edit/stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: inputText.trim(),
                    action,
                    instruction: instruction.trim(),
                }),
            });

            const reader = res.body?.getReader();
            const decoder = new TextDecoder();
            if (!reader) return;

            let buffer = '';
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    try {
                        const data = JSON.parse(line.slice(6));
                        if (data.type === 'chunk')
                            setResult((prev) => prev + data.content);
                    } catch { }
                }
            }
        } catch (e) {
            console.error(e);
            setResult('处理失败，请重试。');
        }
        setLoading(false);
    };

    const handleCopy = () => {
        navigator.clipboard.writeText(result);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    return (
        <div className="min-h-screen bg-slate-50 dark:bg-slate-900 p-8 transition-colors">
            <div className="max-w-5xl mx-auto">
                {/* Header */}
                <div className="mb-8">
                    <h1 className="text-2xl font-bold text-slate-800 dark:text-white mb-2 flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-rose-500 to-pink-400 flex items-center justify-center text-white shadow-lg">
                            <PenTool size={20} />
                        </div>
                        协同写作
                    </h1>
                    <p className="text-slate-500 dark:text-slate-400">
                        AI 辅助文本改写、扩展、精简和润色
                    </p>
                </div>

                {/* Action selector */}
                <div className="grid grid-cols-4 gap-3 mb-6">
                    {actions.map(({ key, label, icon: Icon, desc }) => (
                        <button
                            key={key}
                            onClick={() => setAction(key)}
                            className={`p-4 rounded-xl border text-left transition-all ${action === key
                                    ? 'border-rose-300 dark:border-rose-700 bg-rose-50 dark:bg-rose-900/20 shadow-sm'
                                    : 'border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 hover:border-slate-300 dark:hover:border-slate-600'
                                }`}
                        >
                            <Icon
                                size={18}
                                className={
                                    action === key
                                        ? 'text-rose-500 mb-2'
                                        : 'text-slate-400 mb-2'
                                }
                            />
                            <p
                                className={`font-medium text-sm ${action === key
                                        ? 'text-rose-700 dark:text-rose-300'
                                        : 'text-slate-700 dark:text-slate-200'
                                    }`}
                            >
                                {label}
                            </p>
                            <p className="text-xs text-slate-400 mt-0.5">
                                {desc}
                            </p>
                        </button>
                    ))}
                </div>

                {/* Editor panels */}
                <div className="grid grid-cols-2 gap-6">
                    {/* Input */}
                    <div className="flex flex-col">
                        <label className="text-sm font-medium text-slate-600 dark:text-slate-300 mb-2">
                            原文
                        </label>
                        <textarea
                            value={inputText}
                            onChange={(e) => setInputText(e.target.value)}
                            placeholder="粘贴或输入需要处理的文本..."
                            rows={12}
                            className="flex-1 px-4 py-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 placeholder-slate-400 resize-none focus:outline-none focus:ring-2 focus:ring-rose-500 text-sm leading-relaxed"
                        />
                        {action === 'rewrite' && (
                            <input
                                value={instruction}
                                onChange={(e) => setInstruction(e.target.value)}
                                placeholder="改写指令（可选），例如：更加学术化"
                                className="mt-3 px-4 py-2.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 placeholder-slate-400 text-sm focus:outline-none focus:ring-2 focus:ring-rose-500"
                            />
                        )}
                        <button
                            onClick={handleEdit}
                            disabled={loading || !inputText.trim()}
                            className="mt-3 py-3 bg-gradient-to-r from-rose-500 to-pink-500 text-white rounded-xl font-medium hover:from-rose-600 hover:to-pink-600 disabled:opacity-50 transition-all flex items-center justify-center gap-2"
                        >
                            {loading ? (
                                <Loader2 size={18} className="animate-spin" />
                            ) : (
                                <PenTool size={18} />
                            )}
                            {actions.find((a) => a.key === action)?.label || '处理'}
                        </button>
                    </div>

                    {/* Output */}
                    <div className="flex flex-col">
                        <div className="flex items-center justify-between mb-2">
                            <label className="text-sm font-medium text-slate-600 dark:text-slate-300">
                                结果
                            </label>
                            {result && (
                                <button
                                    onClick={handleCopy}
                                    className="text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 flex items-center gap-1 transition-colors"
                                >
                                    {copied ? (
                                        <>
                                            <Check size={12} /> 已复制
                                        </>
                                    ) : (
                                        <>
                                            <Copy size={12} /> 复制
                                        </>
                                    )}
                                </button>
                            )}
                        </div>
                        <div className="flex-1 px-4 py-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm text-slate-700 dark:text-slate-200 leading-relaxed overflow-y-auto min-h-[320px]">
                            {result ? (
                                <pre className="whitespace-pre-wrap font-sans">
                                    {result}
                                </pre>
                            ) : loading ? (
                                <div className="flex items-center justify-center h-full text-slate-400">
                                    <Loader2
                                        size={24}
                                        className="animate-spin"
                                    />
                                </div>
                            ) : (
                                <p className="text-slate-400 text-center mt-24">
                                    处理结果将显示在这里
                                </p>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
