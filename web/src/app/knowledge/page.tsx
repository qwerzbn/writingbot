'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAppContext } from '@/context/AppContext';
import { Plus, Trash2 } from 'lucide-react';

export default function KnowledgePage() {
    const { kbs, refreshKbs } = useAppContext();
    const router = useRouter();
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [newKbName, setNewKbName] = useState('');
    const [newKbDesc, setNewKbDesc] = useState('');
    const [newKbProvider, setNewKbProvider] = useState('sentence-transformers');
    const [newKbModel, setNewKbModel] = useState('sentence-transformers/all-mpnet-base-v2');
    const [isCreating, setIsCreating] = useState(false);

    useEffect(() => {
        refreshKbs();
    }, []);

    // Reset model when provider changes
    const handleProviderChange = (provider: string) => {
        setNewKbProvider(provider);
        if (provider === 'ollama') {
            setNewKbModel('nomic-embed-text:latest');
        } else if (provider === 'openai') {
            setNewKbModel('text-embedding-3-small');
        } else {
            setNewKbModel('sentence-transformers/all-mpnet-base-v2');
        }
    };

    const handleCreateKb = async () => {
        if (!newKbName.trim()) return;
        setIsCreating(true);
        try {
            const res = await fetch('/api/kbs', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: newKbName,
                    description: newKbDesc,
                    embedding_provider: newKbProvider,
                    embedding_model: newKbModel,
                }),
            });
            const data = await res.json();
            if (data.success) {
                setShowCreateModal(false);
                setNewKbName('');
                setNewKbDesc('');
                // Reset to default
                handleProviderChange('sentence-transformers');
                refreshKbs();
            }
        } catch (e) {
            console.error(e);
        } finally {
            setIsCreating(false);
        }
    };

    const handleDeleteKb = async (id: string, e: React.MouseEvent) => {
        e.stopPropagation();
        if (!confirm('确定要删除这个知识库吗？')) return;
        try {
            await fetch(`/api/kbs/${id}`, { method: 'DELETE' });
            refreshKbs();
        } catch (e) {
            console.error(e);
        }
    };

    return (
        <div className="h-full flex flex-col">
            {/* Header */}
            <header className="h-18 px-8 flex items-center justify-between bg-white border-b border-slate-200">
                <h1 className="text-xl font-semibold text-slate-800">知识库管理</h1>
                <button
                    onClick={() => setShowCreateModal(true)}
                    className="flex items-center gap-2 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors shadow-sm"
                >
                    <Plus size={18} />
                    新建知识库
                </button>
            </header>

            {/* Content */}
            <div className="flex-1 p-8 overflow-y-auto">
                {kbs.length === 0 ? (
                    <div className="text-center text-slate-500 py-16">
                        <p>暂无知识库，请点击右上角新建</p>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {kbs.map((kb) => (
                            <div
                                key={kb.id}
                                onClick={() => router.push(`/knowledge/${kb.id}`)}
                                className="bg-white rounded-xl border border-slate-200 p-6 cursor-pointer hover:shadow-md hover:border-blue-300 transition-all group relative"
                            >
                                <button
                                    onClick={(e) => handleDeleteKb(kb.id, e)}
                                    className="absolute top-4 right-4 p-2 rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-50 opacity-0 group-hover:opacity-100 transition-all"
                                >
                                    <Trash2 size={16} />
                                </button>
                                <div className="w-12 h-12 bg-blue-100 text-blue-500 rounded-lg flex items-center justify-center text-xl mb-4">
                                    📚
                                </div>
                                <h3 className="text-lg font-semibold text-slate-800 mb-1">{kb.name}</h3>
                                <p className="text-sm text-slate-500 mb-4 line-clamp-2">{kb.description || '无描述'}</p>
                                <div className="flex gap-2">
                                    <span className="px-2 py-1 bg-slate-100 text-slate-600 text-xs rounded-full">
                                        {kb.files?.length || 0} 文档
                                    </span>
                                    <span className="px-2 py-1 bg-slate-100 text-slate-600 text-xs rounded-full">
                                        {kb.embedding_model.split('/').pop()}
                                    </span>
                                    {kb.embedding_provider && (
                                        <span className="px-2 py-1 bg-blue-50 text-blue-600 text-xs rounded-full">
                                            {kb.embedding_provider}
                                        </span>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* Create Modal */}
            {showCreateModal && (
                <>
                    <div className="fixed inset-0 bg-black/40 z-40" onClick={() => setShowCreateModal(false)} />
                    <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white rounded-xl shadow-xl w-full max-w-md z-50 animate-in fade-in zoom-in-95">
                        <div className="p-6 border-b border-slate-200">
                            <h3 className="text-lg font-semibold">新建知识库</h3>
                        </div>
                        <div className="p-6 space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">知识库名称</label>
                                <input
                                    type="text"
                                    value={newKbName}
                                    onChange={(e) => setNewKbName(e.target.value)}
                                    placeholder="例如：2024 AI 论文集"
                                    className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">描述 (可选)</label>
                                <textarea
                                    value={newKbDesc}
                                    onChange={(e) => setNewKbDesc(e.target.value)}
                                    placeholder="关于该知识库的描述..."
                                    className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none resize-none h-20"
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">Embedding Provider</label>
                                <select
                                    value={newKbProvider}
                                    onChange={(e) => handleProviderChange(e.target.value)}
                                    className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none mb-3"
                                >
                                    <option value="sentence-transformers">Local (HuggingFace)</option>
                                    <option value="ollama">Ollama (Local)</option>
                                    <option value="openai">OpenAI (API)</option>
                                </select>

                                <label className="block text-sm font-medium text-slate-700 mb-1">Embedding Model</label>
                                {newKbProvider === 'sentence-transformers' && (
                                    <select
                                        value={newKbModel}
                                        onChange={(e) => setNewKbModel(e.target.value)}
                                        className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                                    >
                                        <option value="sentence-transformers/all-mpnet-base-v2">all-mpnet-base-v2 (推荐)</option>
                                        <option value="sentence-transformers/all-MiniLM-L6-v2">all-MiniLM-L6-v2 (快速)</option>
                                    </select>
                                )}
                                {newKbProvider === 'ollama' && (
                                    <input
                                        type="text"
                                        value={newKbModel}
                                        onChange={(e) => setNewKbModel(e.target.value)}
                                        placeholder="例如: nomic-embed-text"
                                        className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                                    />
                                )}
                                {newKbProvider === 'openai' && (
                                    <select
                                        value={newKbModel}
                                        onChange={(e) => setNewKbModel(e.target.value)}
                                        className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                                    >
                                        <option value="text-embedding-3-small">text-embedding-3-small</option>
                                        <option value="text-embedding-3-large">text-embedding-3-large</option>
                                        <option value="text-embedding-ada-002">text-embedding-ada-002 (旧版)</option>
                                    </select>
                                )}
                            </div>
                        </div>
                        <div className="p-4 bg-slate-50 rounded-b-xl flex justify-end gap-3">
                            <button
                                onClick={() => setShowCreateModal(false)}
                                className="px-4 py-2 text-slate-600 hover:bg-slate-200 rounded-lg transition-colors"
                            >
                                取消
                            </button>
                            <button
                                onClick={handleCreateKb}
                                disabled={isCreating || !newKbName.trim()}
                                className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                {isCreating ? '创建中...' : '创建'}
                            </button>
                        </div>
                    </div>
                </>
            )}
        </div>
    );
}
