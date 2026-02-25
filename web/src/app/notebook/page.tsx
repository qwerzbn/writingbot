'use client';

import { useState, useEffect } from 'react';
import { Plus, Trash2, BookOpen, ChevronRight } from 'lucide-react';

const API = '/api';

interface NotebookData {
    id: string;
    name: string;
    description: string;
    color: string;
    icon: string;
    record_count?: number;
    records?: RecordData[];
    created_at: string;
    updated_at: string;
}

interface RecordData {
    id: string;
    type: string;
    title: string;
    output: string;
    created_at: string;
}

export default function NotebookPage() {
    const [notebooks, setNotebooks] = useState<NotebookData[]>([]);
    const [selected, setSelected] = useState<NotebookData | null>(null);
    const [newName, setNewName] = useState('');
    const [loading, setLoading] = useState(false);

    const fetchNotebooks = async () => {
        try {
            const res = await fetch(`${API}/notebooks`);
            const data = await res.json();
            if (data.success) setNotebooks(data.data);
        } catch (e) {
            console.error(e);
        }
    };

    const fetchNotebook = async (id: string) => {
        try {
            const res = await fetch(`${API}/notebooks/${id}`);
            const data = await res.json();
            if (data.success) setSelected(data.data);
        } catch (e) {
            console.error(e);
        }
    };

    const createNotebook = async () => {
        if (!newName.trim()) return;
        setLoading(true);
        try {
            const res = await fetch(`${API}/notebooks`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: newName.trim() }),
            });
            const data = await res.json();
            if (data.success) {
                setNewName('');
                fetchNotebooks();
            }
        } catch (e) {
            console.error(e);
        }
        setLoading(false);
    };

    const deleteNotebook = async (id: string) => {
        if (!confirm('确定删除此笔记本？')) return;
        try {
            await fetch(`${API}/notebooks/${id}`, { method: 'DELETE' });
            if (selected?.id === id) setSelected(null);
            fetchNotebooks();
        } catch (e) {
            console.error(e);
        }
    };

    useEffect(() => {
        fetchNotebooks();
    }, []);

    return (
        <div className="min-h-screen bg-slate-50 dark:bg-slate-900 flex transition-colors">
            {/* Notebook list */}
            <div className="w-80 border-r border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 flex flex-col">
                <div className="p-4 border-b border-slate-200 dark:border-slate-700">
                    <h1 className="text-lg font-bold text-slate-800 dark:text-white mb-3">
                        📓 笔记本
                    </h1>
                    <div className="flex gap-2">
                        <input
                            value={newName}
                            onChange={(e) => setNewName(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && createNotebook()}
                            placeholder="新建笔记本..."
                            className="flex-1 px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                        />
                        <button
                            onClick={createNotebook}
                            disabled={loading || !newName.trim()}
                            className="px-3 py-2 bg-blue-500 text-white rounded-lg text-sm hover:bg-blue-600 disabled:opacity-50 transition-colors"
                        >
                            <Plus size={16} />
                        </button>
                    </div>
                </div>
                <div className="flex-1 overflow-y-auto">
                    {notebooks.length === 0 ? (
                        <p className="p-4 text-sm text-slate-400 text-center">
                            暂无笔记本
                        </p>
                    ) : (
                        notebooks.map((nb) => (
                            <div
                                key={nb.id}
                                onClick={() => fetchNotebook(nb.id)}
                                className={`px-4 py-3 cursor-pointer border-b border-slate-100 dark:border-slate-700 flex items-center justify-between group hover:bg-slate-50 dark:hover:bg-slate-750 transition-colors ${selected?.id === nb.id
                                        ? 'bg-blue-50 dark:bg-blue-900/20 border-l-2 border-l-blue-500'
                                        : ''
                                    }`}
                            >
                                <div className="flex items-center gap-3 min-w-0">
                                    <BookOpen
                                        size={18}
                                        className="text-slate-400 shrink-0"
                                    />
                                    <div className="min-w-0">
                                        <p className="font-medium text-slate-700 dark:text-slate-200 truncate text-sm">
                                            {nb.name}
                                        </p>
                                        <p className="text-xs text-slate-400">
                                            {nb.record_count || 0} 条记录
                                        </p>
                                    </div>
                                </div>
                                <button
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        deleteNotebook(nb.id);
                                    }}
                                    className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-red-500 transition-all"
                                >
                                    <Trash2 size={14} />
                                </button>
                            </div>
                        ))
                    )}
                </div>
            </div>

            {/* Detail */}
            <div className="flex-1 p-8">
                {selected ? (
                    <div>
                        <h2 className="text-2xl font-bold text-slate-800 dark:text-white mb-2">
                            {selected.name}
                        </h2>
                        <p className="text-slate-500 dark:text-slate-400 mb-6 text-sm">
                            {selected.description || '暂无描述'}
                        </p>

                        <h3 className="text-sm font-semibold text-slate-600 dark:text-slate-300 mb-3 uppercase tracking-wide">
                            记录列表
                        </h3>
                        {!selected.records || selected.records.length === 0 ? (
                            <p className="text-slate-400 text-sm">
                                暂无记录。在对话、研究或写作时可将结果保存到此笔记本。
                            </p>
                        ) : (
                            <div className="space-y-3">
                                {selected.records.map((r) => (
                                    <div
                                        key={r.id}
                                        className="bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 p-4"
                                    >
                                        <div className="flex items-center gap-2 mb-2">
                                            <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400">
                                                {r.type}
                                            </span>
                                            <span className="font-medium text-slate-700 dark:text-slate-200 text-sm">
                                                {r.title}
                                            </span>
                                        </div>
                                        <p className="text-sm text-slate-500 dark:text-slate-400 line-clamp-3">
                                            {r.output}
                                        </p>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                ) : (
                    <div className="flex flex-col items-center justify-center h-full text-slate-400">
                        <BookOpen size={48} className="mb-4 opacity-30" />
                        <p>选择或创建一个笔记本</p>
                    </div>
                )}
            </div>
        </div>
    );
}
