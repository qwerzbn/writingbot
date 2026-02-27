'use client';

import { useState } from 'react';
import { useAppContext } from '@/context/AppContext';
import { Search, Loader2, Send, FileText } from 'lucide-react';
import MarkdownRenderer from '@/components/MarkdownRenderer';

const API_BASE = '';

export default function ResearchPage() {
    const { kbs, selectedKbId, setSelectedKbId } = useAppContext();
    const [topic, setTopic] = useState('');
    const [plan, setPlan] = useState('');
    const [report, setReport] = useState('');
    const [sources, setSources] = useState<any[]>([]);
    const [loading, setLoading] = useState(false);

    const handleResearch = async () => {
        if (!topic.trim() || loading) return;
        setLoading(true);
        setPlan('');
        setReport('');
        setSources([]);

        try {
            const res = await fetch(`${API_BASE}/api/research/stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    topic: topic.trim(),
                    kb_id: selectedKbId || undefined,
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
                        if (data.type === 'plan') setPlan(data.content);
                        else if (data.type === 'chunk')
                            setReport((prev) => prev + data.content);
                        else if (data.type === 'sources')
                            setSources(data.data || []);
                    } catch { }
                }
            }
        } catch (e) {
            console.error(e);
            setReport('研究报告生成失败，请重试。');
        }
        setLoading(false);
    };

    return (
        <div className="min-h-screen bg-slate-50 dark:bg-slate-900 p-8 transition-colors">
            <div className="max-w-4xl mx-auto">
                {/* Header */}
                <div className="mb-8">
                    <h1 className="text-2xl font-bold text-slate-800 dark:text-white mb-2 flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-400 flex items-center justify-center text-white shadow-lg">
                            <Search size={20} />
                        </div>
                        深度研究
                    </h1>
                    <p className="text-slate-500 dark:text-slate-400">
                        输入主题，自动生成结构化研究报告
                    </p>
                </div>

                {/* Input */}
                <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-6 mb-6 shadow-sm">
                    <div className="flex gap-3 mb-4">
                        <select
                            value={selectedKbId || ''}
                            onChange={(e) =>
                                setSelectedKbId(e.target.value || null)
                            }
                            className="px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-700 dark:text-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                        >
                            <option value="">不使用知识库</option>
                            {kbs.map((kb) => (
                                <option key={kb.id} value={kb.id}>
                                    {kb.name}
                                </option>
                            ))}
                        </select>
                    </div>
                    <div className="flex gap-3">
                        <input
                            value={topic}
                            onChange={(e) => setTopic(e.target.value)}
                            onKeyDown={(e) =>
                                e.key === 'Enter' && handleResearch()
                            }
                            placeholder="输入研究主题，例如：Transformer 架构在 NLP 中的应用"
                            className="flex-1 px-4 py-3 rounded-lg border border-slate-200 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                        />
                        <button
                            onClick={handleResearch}
                            disabled={loading || !topic.trim()}
                            className="px-6 py-3 bg-gradient-to-r from-emerald-500 to-teal-500 text-white rounded-lg font-medium hover:from-emerald-600 hover:to-teal-600 disabled:opacity-50 transition-all flex items-center gap-2"
                        >
                            {loading ? (
                                <Loader2 size={18} className="animate-spin" />
                            ) : (
                                <Send size={18} />
                            )}
                            生成报告
                        </button>
                    </div>
                </div>

                {/* Plan */}
                {plan && (
                    <div className="bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800 rounded-xl p-5 mb-6">
                        <h3 className="text-sm font-semibold text-emerald-700 dark:text-emerald-400 mb-2">
                            📋 研究计划
                        </h3>
                        <MarkdownRenderer content={plan} />
                    </div>
                )}

                {/* Report */}
                {report && (
                    <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-6 shadow-sm">
                        <h3 className="text-sm font-semibold text-slate-600 dark:text-slate-300 mb-4 flex items-center gap-2">
                            <FileText size={16} /> 研究报告
                        </h3>
                        <MarkdownRenderer content={report} />
                    </div>
                )}

                {/* Loading placeholder */}
                {loading && !report && (
                    <div className="text-center py-16 text-slate-400">
                        <Loader2
                            size={32}
                            className="animate-spin mx-auto mb-4"
                        />
                        <p>正在进行深度研究...</p>
                    </div>
                )}
            </div>
        </div>
    );
}
