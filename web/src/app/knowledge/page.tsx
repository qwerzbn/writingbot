'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAppContext } from '@/context/AppContext';
import { Plus, Trash2, CheckCircle, AlertCircle, Loader2, Zap } from 'lucide-react';

export default function KnowledgePage() {
    const { kbs, refreshKbs } = useAppContext();
    const router = useRouter();
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [newKbName, setNewKbName] = useState('');
    const [newKbDesc, setNewKbDesc] = useState('');
    const [newKbProvider, setNewKbProvider] = useState('sentence-transformers');
    const [newKbModel, setNewKbModel] = useState('BAAI/bge-m3');
    const [isCreating, setIsCreating] = useState(false);

    // Connection test state
    const [testStatus, setTestStatus] = useState<'idle' | 'testing' | 'success' | 'failed'>('idle');
    const [testError, setTestError] = useState('');
    const [testDimension, setTestDimension] = useState<number | null>(null);

    // Custom API key/base URL (shown when test fails for openai/ollama)
    const [customApiKey, setCustomApiKey] = useState('');
    const [customBaseUrl, setCustomBaseUrl] = useState('');
    const [showApiKeyInput, setShowApiKeyInput] = useState(false);

    useEffect(() => {
        refreshKbs();
    }, [refreshKbs]);

    // Reset model and test state when provider changes
    const handleProviderChange = (provider: string) => {
        setNewKbProvider(provider);
        setTestStatus('idle');
        setTestError('');
        setTestDimension(null);
        setShowApiKeyInput(false);
        setCustomApiKey('');
        setCustomBaseUrl('');
        if (provider === 'ollama') {
            setNewKbModel('nomic-embed-text:latest');
        } else if (provider === 'openai') {
            setNewKbModel('text-embedding-v3');
        } else {
            setNewKbModel('BAAI/bge-m3');
        }
    };

    const handleTestConnection = async () => {
        setTestStatus('testing');
        setTestError('');
        setTestDimension(null);
        try {
            const body: Record<string, string> = {
                embedding_provider: newKbProvider,
                embedding_model: newKbModel,
            };
            if (customApiKey) body.api_key = customApiKey;
            if (customBaseUrl) body.base_url = customBaseUrl;

            const res = await fetch('/api/embedding/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await res.json();
            if (data.success) {
                setTestStatus('success');
                setTestDimension(data.dimension);
            } else {
                setTestStatus('failed');
                setTestError(data.error || '连接失败');
                // Show API key input for openai/ollama if test fails
                if (newKbProvider === 'openai' || newKbProvider === 'ollama') {
                    setShowApiKeyInput(true);
                }
            }
        } catch {
            setTestStatus('failed');
            setTestError('网络错误');
        }
    };

    const handleCreateKb = async () => {
        if (!newKbName.trim()) return;

        // For non-local providers, must pass test first
        if (newKbProvider !== 'sentence-transformers' && testStatus !== 'success') {
            handleTestConnection();
            return;
        }

        setIsCreating(true);
        try {
            const body: Record<string, string> = {
                name: newKbName,
                description: newKbDesc,
                embedding_provider: newKbProvider,
                embedding_model: newKbModel,
            };
            if (customApiKey) body.embedding_api_key = customApiKey;
            if (customBaseUrl) body.embedding_base_url = customBaseUrl;

            const res = await fetch('/api/kbs', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await res.json();
            if (data.success) {
                setShowCreateModal(false);
                setNewKbName('');
                setNewKbDesc('');
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

    const needsTest = newKbProvider !== 'sentence-transformers';
    const canCreate = newKbName.trim() && (!needsTest || testStatus === 'success');

    return (
        <div className="h-full flex flex-col">
            {/* Header */}
            <header className="h-18 px-8 flex items-center justify-between bg-white border-b border-slate-200">
                <h1 className="text-xl font-semibold text-slate-800">知识库管理</h1>
                <button
                    onClick={() => setShowCreateModal(true)}
                    className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-blue-500 to-blue-600 text-white rounded-lg hover:from-blue-600 hover:to-blue-700 transition-all shadow-sm hover:shadow-md text-sm font-medium"
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
                    <div className="fixed inset-0 bg-black/40 z-40 backdrop-blur-sm" onClick={() => setShowCreateModal(false)} />
                    <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white rounded-2xl shadow-2xl w-full max-w-md z-50">
                        <div className="p-6 border-b border-slate-100">
                            <h3 className="text-lg font-semibold text-slate-800">新建知识库</h3>
                        </div>
                        <div className="p-6 space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">知识库名称</label>
                                <input
                                    type="text"
                                    value={newKbName}
                                    onChange={(e) => setNewKbName(e.target.value)}
                                    placeholder="例如：2024 AI 论文集"
                                    className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none text-sm"
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">描述 (可选)</label>
                                <textarea
                                    value={newKbDesc}
                                    onChange={(e) => setNewKbDesc(e.target.value)}
                                    placeholder="关于该知识库的描述..."
                                    className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none resize-none h-20 text-sm"
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">Embedding Provider</label>
                                <select
                                    value={newKbProvider}
                                    onChange={(e) => handleProviderChange(e.target.value)}
                                    className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none mb-3 text-sm"
                                >
                                    <option value="sentence-transformers">Local (HuggingFace)</option>
                                    <option value="ollama">Ollama (Local)</option>
                                    <option value="openai">DashScope (API)</option>
                                </select>

                                <label className="block text-sm font-medium text-slate-700 mb-1">Embedding Model</label>
                                {newKbProvider === 'sentence-transformers' && (
                                    <select
                                        value={newKbModel}
                                        onChange={(e) => setNewKbModel(e.target.value)}
                                        className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none text-sm"
                                    >
                                        <option value="BAAI/bge-m3">BAAI/bge-m3 (高精度多语言)</option>
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
                                        className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none text-sm"
                                    />
                                )}
                                {newKbProvider === 'openai' && (
                                    <>
                                        <input
                                            type="text"
                                            value={newKbModel}
                                            onChange={(e) => { setNewKbModel(e.target.value); setTestStatus('idle'); }}
                                            placeholder="例如: text-embedding-v3"
                                            className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none text-sm"
                                        />
                                        <p className="text-[11px] text-slate-400 mt-1">
                                            推荐: text-embedding-v3 · 可用: text-embedding-v2 / v1
                                        </p>
                                    </>
                                )}
                            </div>

                            {/* Custom API key / Base URL (shown for openai/ollama, or after failure) */}
                            {showApiKeyInput && (newKbProvider === 'openai' || newKbProvider === 'ollama') && (
                                <div className="space-y-3 p-3 bg-amber-50 rounded-lg border border-amber-200">
                                    <p className="text-xs text-amber-700 font-medium">连接失败，请填写 API 配置：</p>
                                    {newKbProvider === 'openai' && (
                                        <div>
                                            <label className="block text-xs font-medium text-slate-600 mb-1">API Base URL (可选)</label>
                                            <input
                                                type="text"
                                                value={customBaseUrl}
                                                onChange={(e) => { setCustomBaseUrl(e.target.value); setTestStatus('idle'); }}
                                                placeholder="例如: https://api.openai.com/v1"
                                                className="w-full px-3 py-1.5 border border-slate-300 rounded-lg text-xs outline-none focus:ring-2 focus:ring-blue-500"
                                            />
                                        </div>
                                    )}
                                    <div>
                                        <label className="block text-xs font-medium text-slate-600 mb-1">API Key</label>
                                        <input
                                            type="password"
                                            value={customApiKey}
                                            onChange={(e) => { setCustomApiKey(e.target.value); setTestStatus('idle'); }}
                                            placeholder="sk-..."
                                            className="w-full px-3 py-1.5 border border-slate-300 rounded-lg text-xs outline-none focus:ring-2 focus:ring-blue-500"
                                        />
                                    </div>
                                </div>
                            )}

                            {/* Test connection button for non-local providers */}
                            {needsTest && (
                                <div className="flex items-center gap-3">
                                    <button
                                        onClick={handleTestConnection}
                                        disabled={testStatus === 'testing'}
                                        className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors disabled:opacity-50 disabled:cursor-not-allowed bg-white border-slate-300 text-slate-700 hover:bg-slate-50"
                                    >
                                        {testStatus === 'testing' ? (
                                            <><Loader2 size={13} className="animate-spin" /> 测试中...</>
                                        ) : (
                                            <><Zap size={13} /> 测试连接</>
                                        )}
                                    </button>
                                    {testStatus === 'success' && (
                                        <span className="flex items-center gap-1 text-xs text-emerald-600">
                                            <CheckCircle size={13} /> 连接成功 (dim={testDimension})
                                        </span>
                                    )}
                                    {testStatus === 'failed' && (
                                        <span className="flex items-center gap-1 text-xs text-red-500 max-w-[220px] truncate" title={testError}>
                                            <AlertCircle size={13} className="shrink-0" /> {testError}
                                        </span>
                                    )}
                                </div>
                            )}
                        </div>
                        <div className="p-4 bg-slate-50 rounded-b-2xl flex justify-end gap-3 border-t border-slate-100">
                            <button
                                onClick={() => { setShowCreateModal(false); handleProviderChange('sentence-transformers'); }}
                                className="px-4 py-2 text-sm text-slate-600 hover:bg-slate-200 rounded-lg transition-colors"
                            >
                                取消
                            </button>
                            <button
                                onClick={handleCreateKb}
                                disabled={isCreating || !canCreate}
                                className="px-5 py-2 text-sm bg-gradient-to-r from-blue-500 to-blue-600 text-white rounded-lg hover:from-blue-600 hover:to-blue-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-sm font-medium"
                            >
                                {isCreating ? '创建中...' : needsTest && testStatus !== 'success' ? '测试并创建' : '创建'}
                            </button>
                        </div>
                    </div>
                </>
            )}
        </div>
    );
}
