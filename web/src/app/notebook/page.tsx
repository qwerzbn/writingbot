'use client';

import { useState, useEffect } from 'react';
import { Plus, Trash2, BookOpen, Edit3, Check, X } from 'lucide-react';

const API_BASE = 'http://localhost:5001';

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
    user_query: string;
    output: string;
    created_at: string;
}

export default function NotebookPage() {
    const [notebooks, setNotebooks] = useState<NotebookData[]>([]);
    const [selected, setSelected] = useState<NotebookData | null>(null);
    const [newName, setNewName] = useState('');
    const [newDesc, setNewDesc] = useState('');
    const [loading, setLoading] = useState(false);
    const [showCreate, setShowCreate] = useState(false);
    const [editingId, setEditingId] = useState<string | null>(null);
    const [editName, setEditName] = useState('');

    const fetchNotebooks = async () => {
        try {
            const res = await fetch(`${API_BASE}/api/notebooks`);
            const data = await res.json();
            if (data.success) setNotebooks(data.data);
        } catch (e) {
            console.error('Failed to fetch notebooks:', e);
        }
    };

    const fetchNotebook = async (id: string) => {
        try {
            const res = await fetch(`${API_BASE}/api/notebooks/${id}`);
            const data = await res.json();
            if (data.success) setSelected(data.data);
        } catch (e) {
            console.error('Failed to fetch notebook:', e);
        }
    };

    const createNotebook = async () => {
        if (!newName.trim()) return;
        setLoading(true);
        try {
            const res = await fetch(`${API_BASE}/api/notebooks`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: newName.trim(),
                    description: newDesc.trim(),
                }),
            });
            const data = await res.json();
            if (data.success) {
                setNewName('');
                setNewDesc('');
                setShowCreate(false);
                fetchNotebooks();
            }
        } catch (e) {
            console.error('Failed to create notebook:', e);
        }
        setLoading(false);
    };

    const deleteNotebook = async (id: string) => {
        if (!confirm('确定删除此笔记本？所有记录将被清除。')) return;
        try {
            await fetch(`${API_BASE}/api/notebooks/${id}`, {
                method: 'DELETE',
            });
            if (selected?.id === id) setSelected(null);
            fetchNotebooks();
        } catch (e) {
            console.error('Failed to delete notebook:', e);
        }
    };

    const renameNotebook = async (id: string) => {
        if (!editName.trim()) return;
        try {
            const res = await fetch(`${API_BASE}/api/notebooks/${id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: editName.trim() }),
            });
            const data = await res.json();
            if (data.success) {
                setEditingId(null);
                fetchNotebooks();
                if (selected?.id === id) fetchNotebook(id);
            }
        } catch (e) {
            console.error('Failed to rename notebook:', e);
        }
    };

    const deleteRecord = async (notebookId: string, recordId: string) => {
        try {
            await fetch(
                `${API_BASE}/api/notebooks/${notebookId}/records/${recordId}`,
                { method: 'DELETE' }
            );
            fetchNotebook(notebookId);
        } catch (e) {
            console.error('Failed to delete record:', e);
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
                    <div className="flex items-center justify-between mb-3">
                        <h1 className="text-lg font-bold text-slate-800 dark:text-white">
                            📓 笔记本
                        </h1>
                        <button
                            onClick={() => setShowCreate(!showCreate)}
                            className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 transition-colors"
                            title="新建笔记本"
                        >
                            <Plus size={18} />
                        </button>
                    </div>

                    {/* Create form */}
                    {showCreate && (
                        <div className="space-y-2 p-3 bg-slate-50 dark:bg-slate-700 rounded-lg">
                            <input
                                value={newName}
                                onChange={(e) => setNewName(e.target.value)}
                                onKeyDown={(e) =>
                                    e.key === 'Enter' && createNotebook()
                                }
                                placeholder="笔记本名称"
                                autoFocus
                                className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-800 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                            />
                            <input
                                value={newDesc}
                                onChange={(e) => setNewDesc(e.target.value)}
                                placeholder="描述（可选）"
                                className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-800 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                            />
                            <div className="flex gap-2">
                                <button
                                    onClick={createNotebook}
                                    disabled={loading || !newName.trim()}
                                    className="flex-1 px-3 py-2 bg-blue-500 text-white rounded-lg text-sm hover:bg-blue-600 disabled:opacity-50 transition-colors font-medium"
                                >
                                    创建
                                </button>
                                <button
                                    onClick={() => {
                                        setShowCreate(false);
                                        setNewName('');
                                        setNewDesc('');
                                    }}
                                    className="px-3 py-2 bg-slate-200 dark:bg-slate-600 text-slate-600 dark:text-slate-200 rounded-lg text-sm hover:bg-slate-300 dark:hover:bg-slate-500 transition-colors"
                                >
                                    取消
                                </button>
                            </div>
                        </div>
                    )}
                </div>

                {/* Notebook list */}
                <div className="flex-1 overflow-y-auto">
                    {notebooks.length === 0 ? (
                        <div className="p-6 text-center text-slate-400">
                            <BookOpen
                                size={32}
                                className="mx-auto mb-2 opacity-30"
                            />
                            <p className="text-sm">暂无笔记本</p>
                            <p className="text-xs mt-1">
                                点击 + 创建第一个笔记本
                            </p>
                        </div>
                    ) : (
                        notebooks.map((nb) => (
                            <div
                                key={nb.id}
                                onClick={() => fetchNotebook(nb.id)}
                                className={`px-4 py-3 cursor-pointer border-b border-slate-100 dark:border-slate-700 flex items-center justify-between group hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors ${selected?.id === nb.id
                                        ? 'bg-blue-50 dark:bg-blue-900/20 border-l-2 border-l-blue-500'
                                        : ''
                                    }`}
                            >
                                <div className="flex items-center gap-3 min-w-0 flex-1">
                                    <div
                                        className="w-8 h-8 rounded-lg flex items-center justify-center text-white text-sm shrink-0"
                                        style={{
                                            backgroundColor:
                                                nb.color || '#3B82F6',
                                        }}
                                    >
                                        📓
                                    </div>
                                    <div className="min-w-0 flex-1">
                                        {editingId === nb.id ? (
                                            <div className="flex items-center gap-1">
                                                <input
                                                    value={editName}
                                                    onChange={(e) =>
                                                        setEditName(
                                                            e.target.value
                                                        )
                                                    }
                                                    onKeyDown={(e) => {
                                                        if (e.key === 'Enter')
                                                            renameNotebook(
                                                                nb.id
                                                            );
                                                        if (e.key === 'Escape')
                                                            setEditingId(null);
                                                    }}
                                                    onClick={(e) =>
                                                        e.stopPropagation()
                                                    }
                                                    autoFocus
                                                    className="flex-1 px-1 py-0.5 text-sm rounded border border-blue-300 dark:border-blue-600 bg-white dark:bg-slate-800 text-slate-700 dark:text-white outline-none"
                                                />
                                                <button
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        renameNotebook(nb.id);
                                                    }}
                                                    className="text-green-500 hover:text-green-600"
                                                >
                                                    <Check size={14} />
                                                </button>
                                                <button
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        setEditingId(null);
                                                    }}
                                                    className="text-slate-400 hover:text-slate-600"
                                                >
                                                    <X size={14} />
                                                </button>
                                            </div>
                                        ) : (
                                            <>
                                                <p className="font-medium text-slate-700 dark:text-slate-200 truncate text-sm">
                                                    {nb.name}
                                                </p>
                                                <p className="text-xs text-slate-400">
                                                    {nb.record_count || 0}{' '}
                                                    条记录
                                                </p>
                                            </>
                                        )}
                                    </div>
                                </div>
                                {editingId !== nb.id && (
                                    <div className="opacity-0 group-hover:opacity-100 flex items-center gap-1 transition-all">
                                        <button
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                setEditingId(nb.id);
                                                setEditName(nb.name);
                                            }}
                                            className="p-1 rounded text-slate-400 hover:text-blue-500 transition-colors"
                                            title="重命名"
                                        >
                                            <Edit3 size={13} />
                                        </button>
                                        <button
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                deleteNotebook(nb.id);
                                            }}
                                            className="p-1 rounded text-slate-400 hover:text-red-500 transition-colors"
                                            title="删除"
                                        >
                                            <Trash2 size={13} />
                                        </button>
                                    </div>
                                )}
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
                            记录列表 ({selected.records?.length || 0})
                        </h3>

                        {!selected.records || selected.records.length === 0 ? (
                            <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-8 text-center">
                                <BookOpen
                                    size={36}
                                    className="mx-auto mb-3 text-slate-300 dark:text-slate-600"
                                />
                                <p className="text-slate-400 text-sm mb-1">
                                    暂无记录
                                </p>
                                <p className="text-slate-400 text-xs">
                                    在对话、研究或写作时可将结果保存到此笔记本
                                </p>
                            </div>
                        ) : (
                            <div className="space-y-3">
                                {selected.records.map((r) => (
                                    <div
                                        key={r.id}
                                        className="group bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 p-4"
                                    >
                                        <div className="flex items-center justify-between mb-2">
                                            <div className="flex items-center gap-2">
                                                <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 font-medium">
                                                    {r.type}
                                                </span>
                                                <span className="font-medium text-slate-700 dark:text-slate-200 text-sm">
                                                    {r.title}
                                                </span>
                                            </div>
                                            <button
                                                onClick={() =>
                                                    deleteRecord(
                                                        selected.id,
                                                        r.id
                                                    )
                                                }
                                                className="opacity-0 group-hover:opacity-100 p-1 rounded text-slate-400 hover:text-red-500 transition-all"
                                                title="删除记录"
                                            >
                                                <Trash2 size={14} />
                                            </button>
                                        </div>
                                        {r.user_query && (
                                            <p className="text-xs text-slate-400 dark:text-slate-500 mb-1">
                                                提问：{r.user_query}
                                            </p>
                                        )}
                                        <p className="text-sm text-slate-600 dark:text-slate-300 line-clamp-4 whitespace-pre-wrap">
                                            {r.output}
                                        </p>
                                        <p className="text-xs text-slate-400 mt-2">
                                            {new Date(
                                                r.created_at
                                            ).toLocaleString('zh-CN')}
                                        </p>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                ) : (
                    <div className="flex flex-col items-center justify-center h-full text-slate-400">
                        <BookOpen size={48} className="mb-4 opacity-30" />
                        <p className="text-lg mb-1">选择或创建一个笔记本</p>
                        <p className="text-sm">
                            笔记本用于保存对话、研究报告和写作记录
                        </p>
                    </div>
                )}
            </div>
        </div>
    );
}
