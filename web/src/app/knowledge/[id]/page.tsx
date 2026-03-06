'use client';

import { useEffect, useState, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useAppContext } from '@/context/AppContext';
import { ArrowLeft, Upload, Trash2, X, CheckCircle, AlertCircle, Loader2, FileText, Eye, Pencil, Check, FileUp, Calendar, Database, Hash } from 'lucide-react';
import dynamic from 'next/dynamic';
const PdfViewer = dynamic(() => import('@/components/chat/PdfViewer'), { ssr: false });

interface KBDetail {
    id: string;
    name: string;
    description?: string;
    embedding_model: string;
    embedding_provider?: string;
    created_at?: string;
    files: FileInfo[];
}

interface FileInfo {
    id: string;
    name: string;
    size: number;
    chunks: number;
    blocks?: number;
    uploaded_at: string;
}

export default function KBDetailPage() {
    const params = useParams();
    const router = useRouter();
    const { refreshKbs } = useAppContext();
    const [kb, setKb] = useState<KBDetail | null>(null);
    const [loading, setLoading] = useState(true);
    const [showImportModal, setShowImportModal] = useState(false);
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [chunkSize, setChunkSize] = useState(1000);
    const [chunkOverlap, setChunkOverlap] = useState(200);
    const fileInputRef = useRef<HTMLInputElement>(null);

    // Toast notification for background import
    const [toast, setToast] = useState<{
        visible: boolean;
        status: 'importing' | 'success' | 'error';
        fileName: string;
        message?: string;
        progress?: number;
        processing?: boolean;
    } | null>(null);

    // Simulate smoother progress during the backend processing phase (after upload)
    useEffect(() => {
        let interval: NodeJS.Timeout;
        if (toast?.status === 'importing' && toast.processing) {
            interval = setInterval(() => {
                setToast(prev => {
                    if (!prev || prev.status !== 'importing' || !prev.processing) {
                        clearInterval(interval);
                        return prev;
                    }
                    const current = prev.progress || 30;
                    if (current >= 99) return prev;

                    const remaining = 99 - current;
                    let increment = 1;
                    if (remaining > 40) increment = 3;
                    else if (remaining > 20) increment = 2;
                    else if (remaining > 10) increment = 1;
                    else increment = Math.random() > 0.5 ? 1 : 0;

                    return { ...prev, progress: Math.min(99, current + increment) };
                });
            }, 1000);
        }
        return () => clearInterval(interval);
    }, [toast?.status, toast?.processing]);

    // Inline editing state
    const [editingFileId, setEditingFileId] = useState<string | null>(null);
    const [editingName, setEditingName] = useState('');

    // PDF viewer
    const [activePdf, setActivePdf] = useState<{ url: string; name: string } | null>(null);

    const kbId = params.id as string;

    const fetchKbDetail = async () => {
        try {
            const res = await fetch(`/api/kbs/${kbId}`);
            const data = await res.json();
            if (data.success) {
                setKb(data.data.metadata);
            }
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchKbDetail();
    }, [kbId]);

    const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files[0]) {
            setSelectedFile(e.target.files[0]);
        }
    };

    const handleUpload = () => {
        if (!selectedFile) return;
        const fileName = selectedFile.name;
        const formData = new FormData();
        formData.append('file', selectedFile);
        formData.append('chunk_size', String(chunkSize));
        formData.append('chunk_overlap', String(chunkOverlap));

        setShowImportModal(false);
        setSelectedFile(null);
        setToast({ visible: true, status: 'importing', fileName, progress: 0, processing: false });

        const xhr = new XMLHttpRequest();
        const backendUrl = `http://${window.location.hostname}:5001/api/kbs/${kbId}/ingest`;
        xhr.open('POST', backendUrl, true);

        // Upload progress (map to 0-30% of total progress)
        xhr.upload.onprogress = (e) => {
            if (e.lengthComputable) {
                const percentComplete = Math.round((e.loaded / e.total) * 100);
                const mappedProgress = Math.floor(percentComplete * 0.3);
                setToast(prev => prev ? { ...prev, progress: mappedProgress } : null);
            }
        };

        xhr.upload.onload = () => {
            // Upload complete, switch to processing mode
            setToast(prev => prev ? { ...prev, progress: 30, processing: true } : null);
        };

        xhr.onload = () => {
            if (xhr.status >= 200 && xhr.status < 300) {
                try {
                    const data = JSON.parse(xhr.responseText);
                    if (data.success) {
                        // Immediately clear the loader and let the re-fetched list show the real document
                        setToast({ visible: true, status: 'success', fileName });
                        fetchKbDetail();
                        refreshKbs();
                        setTimeout(() => setToast(null), 3000);
                    } else {
                        setToast({ visible: true, status: 'error', fileName, message: data.error || data.detail });
                    }
                } catch (e) {
                    setToast({ visible: true, status: 'error', fileName, message: '响应解析失败' });
                }
            } else {
                setToast({ visible: true, status: 'error', fileName, message: `服务器错误 (${xhr.status})` });
            }
        };

        xhr.onerror = () => {
            setToast({ visible: true, status: 'error', fileName, message: '网络错误或文件过大' });
        };

        xhr.send(formData);
    };

    const handleDeleteFile = async (fileId: string, fileName: string) => {
        if (!confirm(`确定要移除文档「${fileName}」吗？`)) return;
        try {
            await fetch(`/api/kbs/${kbId}/files/${fileId}`, { method: 'DELETE' });
            fetchKbDetail();
            refreshKbs();
        } catch (e) {
            console.error(e);
        }
    };

    const handleStartRename = (file: FileInfo) => {
        setEditingFileId(file.id);
        setEditingName(file.name);
    };

    const handleSaveRename = async (fileId: string) => {
        if (!editingName.trim()) return;
        try {
            await fetch(`/api/kbs/${kbId}/files/${fileId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: editingName.trim() }),
            });
            setEditingFileId(null);
            fetchKbDetail();
        } catch (e) {
            console.error(e);
        }
    };

    const handleViewPdf = (file: FileInfo) => {
        setActivePdf({
            url: `/api/kbs/${kbId}/files/${file.id}/content`,
            name: file.name,
        });
    };

    const formatFileSize = (bytes: number) => {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    };

    const formatDate = (dateStr: string) => {
        try {
            return new Date(dateStr).toLocaleDateString('zh-CN', {
                year: 'numeric', month: '2-digit', day: '2-digit',
                hour: '2-digit', minute: '2-digit',
            });
        } catch {
            return dateStr;
        }
    };

    if (loading) {
        return (
            <div className="h-full flex items-center justify-center">
                <div className="flex flex-col items-center gap-3">
                    <Loader2 size={28} className="animate-spin text-blue-500" />
                    <span className="text-sm text-slate-500">加载知识库...</span>
                </div>
            </div>
        );
    }

    if (!kb) {
        return (
            <div className="h-full flex items-center justify-center">
                <div className="text-center">
                    <div className="text-4xl mb-3">📂</div>
                    <p className="text-slate-500">知识库不存在</p>
                    <button onClick={() => router.push('/knowledge')} className="mt-4 text-blue-500 hover:underline text-sm">
                        返回列表
                    </button>
                </div>
            </div>
        );
    }

    return (
        <div className="h-full flex">
            {/* Main content */}
            <div className={`flex-1 flex flex-col transition-all ${activePdf ? 'w-1/2' : 'w-full'}`}>
                {/* Header */}
                <header className="h-16 px-6 flex items-center justify-between bg-white border-b border-slate-200 shrink-0">
                    <div className="flex items-center gap-3">
                        <button
                            onClick={() => router.push('/knowledge')}
                            className="p-2 rounded-lg hover:bg-slate-100 text-slate-500 transition-colors"
                        >
                            <ArrowLeft size={18} />
                        </button>
                        <div>
                            <h1 className="text-lg font-semibold text-slate-800 leading-tight">{kb.name}</h1>
                            {kb.description && (
                                <p className="text-xs text-slate-400 mt-0.5">{kb.description}</p>
                            )}
                        </div>
                    </div>
                    <button
                        onClick={() => setShowImportModal(true)}
                        className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-blue-500 to-blue-600 text-white rounded-lg hover:from-blue-600 hover:to-blue-700 transition-all shadow-sm hover:shadow-md text-sm font-medium"
                    >
                        <Upload size={16} />
                        导入文档
                    </button>
                </header>

                {/* KB Info Cards */}
                <div className="px-6 py-4 bg-slate-50/80 border-b border-slate-100">
                    <div className="flex items-center gap-4">
                        <div className="flex items-center gap-2 px-3 py-1.5 bg-white rounded-lg border border-slate-200 text-xs">
                            <Database size={12} className="text-blue-500" />
                            <span className="text-slate-500">Embedding:</span>
                            <span className="font-medium text-slate-700">{kb.embedding_model.split('/').pop()}</span>
                        </div>
                        {kb.embedding_provider && (
                            <div className="flex items-center gap-2 px-3 py-1.5 bg-white rounded-lg border border-slate-200 text-xs">
                                <span className="text-slate-500">Provider:</span>
                                <span className="font-medium text-slate-700">{kb.embedding_provider}</span>
                            </div>
                        )}
                        <div className="flex items-center gap-2 px-3 py-1.5 bg-white rounded-lg border border-slate-200 text-xs">
                            <FileText size={12} className="text-emerald-500" />
                            <span className="font-medium text-slate-700">{kb.files?.length || 0}</span>
                            <span className="text-slate-500">篇文档</span>
                        </div>
                        {kb.created_at && (
                            <div className="flex items-center gap-2 px-3 py-1.5 bg-white rounded-lg border border-slate-200 text-xs">
                                <Calendar size={12} className="text-amber-500" />
                                <span className="text-slate-500">创建于</span>
                                <span className="font-medium text-slate-700">{formatDate(kb.created_at)}</span>
                            </div>
                        )}
                    </div>
                </div>

                {/* Document List */}
                <div className="flex-1 overflow-y-auto p-6">
                    {(!kb.files || kb.files.length === 0) && toast?.status !== 'importing' ? (
                        <div className="h-full flex flex-col items-center justify-center text-slate-400">
                            <div className="w-20 h-20 rounded-2xl bg-slate-100 flex items-center justify-center mb-4">
                                <FileUp size={32} className="text-slate-300" />
                            </div>
                            <p className="text-base font-medium text-slate-500 mb-1">暂无文档</p>
                            <p className="text-sm text-slate-400 mb-4">点击右上角导入 PDF 文献</p>
                            <button
                                onClick={() => setShowImportModal(true)}
                                className="px-4 py-2 text-sm text-blue-500 hover:bg-blue-50 rounded-lg border border-blue-200 transition-colors"
                            >
                                导入第一篇文档
                            </button>
                        </div>
                    ) : (
                        <div className="space-y-3">
                            {/* Inline Loading / Error Item */}
                            {toast?.visible && toast.status !== 'success' && (
                                <div className={`bg-white rounded-xl border ${toast.status === 'error' ? 'border-red-200 bg-red-50/10' : 'border-blue-200 shadow-[0_0_15px_rgba(59,130,246,0.1)]'} transition-all`}>
                                    <div className="flex flex-col px-5 py-4">
                                        <div className="flex items-center justify-between mb-3">
                                            <div className="flex items-center gap-3">
                                                <div className="w-10 h-10 rounded-lg bg-blue-50 flex items-center justify-center shrink-0">
                                                    {toast.status === 'importing' ? (
                                                        <Loader2 size={20} className="text-blue-500 animate-spin" />
                                                    ) : (
                                                        <AlertCircle size={20} className="text-red-500" />
                                                    )}
                                                </div>
                                                <div>
                                                    <h3 className="text-sm font-medium text-slate-800 truncate max-w-[400px]" title={toast.fileName}>
                                                        {toast.fileName}
                                                    </h3>
                                                    <p className="text-xs text-slate-500 mt-1">
                                                        {toast.status === 'importing' && (toast.processing ? '处理及向量化中...' : '文件上传中...')}
                                                        {toast.status === 'error' && <span className="text-red-500">{toast.message || '导入失败'}</span>}
                                                    </p>
                                                </div>
                                            </div>

                                            <div className="flex items-center gap-4">
                                                {toast.status === 'importing' && (
                                                    <span className="text-sm font-semibold text-blue-600 w-12 text-right">
                                                        {toast.progress || 0}%
                                                    </span>
                                                )}
                                                {toast.status === 'error' && (
                                                    <button onClick={() => setToast(null)} className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-100 transition-colors">
                                                        <X size={16} />
                                                    </button>
                                                )}
                                            </div>
                                        </div>

                                        {/* Progress Bar Line */}
                                        {toast.status === 'importing' && (
                                            <div className="w-full bg-slate-100 rounded-full h-1.5 overflow-hidden">
                                                <div
                                                    className="bg-blue-500 h-1.5 rounded-full transition-all duration-300 ease-out"
                                                    style={{ width: `${toast.progress || 0}%` }}
                                                />
                                            </div>
                                        )}
                                    </div>
                                </div>
                            )}
                            {kb.files.map((file) => (
                                <div
                                    key={file.id}
                                    className="bg-white rounded-xl border border-slate-200 hover:border-slate-300 hover:shadow-sm transition-all group"
                                >
                                    <div className="flex items-center px-5 py-4">
                                        {/* File icon */}
                                        <div className="w-10 h-10 rounded-lg bg-red-50 flex items-center justify-center shrink-0 mr-4">
                                            <FileText size={20} className="text-red-400" />
                                        </div>

                                        {/* File info */}
                                        <div className="flex-1 min-w-0">
                                            {editingFileId === file.id ? (
                                                <div className="flex items-center gap-2">
                                                    <input
                                                        type="text"
                                                        value={editingName}
                                                        onChange={(e) => setEditingName(e.target.value)}
                                                        onKeyDown={(e) => {
                                                            if (e.key === 'Enter') handleSaveRename(file.id);
                                                            if (e.key === 'Escape') setEditingFileId(null);
                                                        }}
                                                        autoFocus
                                                        className="flex-1 px-2 py-1 border border-blue-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                                                    />
                                                    <button
                                                        onClick={() => handleSaveRename(file.id)}
                                                        className="p-1.5 rounded-md bg-blue-500 text-white hover:bg-blue-600 transition-colors"
                                                    >
                                                        <Check size={14} />
                                                    </button>
                                                    <button
                                                        onClick={() => setEditingFileId(null)}
                                                        className="p-1.5 rounded-md text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
                                                    >
                                                        <X size={14} />
                                                    </button>
                                                </div>
                                            ) : (
                                                <>
                                                    <h3 className="text-sm font-medium text-slate-800 truncate" title={file.name}>
                                                        {file.name}
                                                    </h3>
                                                    <div className="flex items-center gap-3 mt-1 text-xs text-slate-400">
                                                        <span>{formatFileSize(file.size)}</span>
                                                        <span className="w-px h-3 bg-slate-200" />
                                                        <span className="flex items-center gap-1">
                                                            <Hash size={10} />
                                                            {file.chunks} chunks
                                                        </span>
                                                        <span className="w-px h-3 bg-slate-200" />
                                                        <span>{formatDate(file.uploaded_at)}</span>
                                                    </div>
                                                </>
                                            )}
                                        </div>

                                        {/* Action buttons */}
                                        {editingFileId !== file.id && (
                                            <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity ml-4">
                                                <button
                                                    onClick={() => handleViewPdf(file)}
                                                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-blue-600 bg-blue-50 hover:bg-blue-100 transition-colors"
                                                    title="查看原文"
                                                >
                                                    <Eye size={13} />
                                                    查看原文
                                                </button>
                                                <button
                                                    onClick={() => handleStartRename(file)}
                                                    className="p-1.5 rounded-lg text-slate-400 hover:text-amber-600 hover:bg-amber-50 transition-colors"
                                                    title="重命名"
                                                >
                                                    <Pencil size={14} />
                                                </button>
                                                <button
                                                    onClick={() => handleDeleteFile(file.id, file.name)}
                                                    className="p-1.5 rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-50 transition-colors"
                                                    title="删除"
                                                >
                                                    <Trash2 size={14} />
                                                </button>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {/* Split-screen PDF Viewer */}
            {activePdf && (
                <PdfViewer
                    fileUrl={activePdf.url}
                    fileName={activePdf.name}
                    onClose={() => setActivePdf(null)}
                />
            )}

            {/* Import Modal */}
            {showImportModal && (
                <>
                    <div className="fixed inset-0 bg-black/40 z-40 backdrop-blur-sm" onClick={() => { setShowImportModal(false); setSelectedFile(null); }} />
                    <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white rounded-2xl shadow-2xl w-full max-w-md z-50">
                        <div className="p-6 border-b border-slate-100 flex justify-between items-center">
                            <h3 className="text-lg font-semibold text-slate-800">导入文档</h3>
                            <button onClick={() => { setShowImportModal(false); setSelectedFile(null); }} className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors">
                                <X size={18} />
                            </button>
                        </div>
                        <div className="p-6 space-y-5">
                            <div
                                onClick={() => fileInputRef.current?.click()}
                                className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all ${selectedFile
                                    ? 'border-blue-300 bg-blue-50/50'
                                    : 'border-slate-200 hover:border-blue-300 hover:bg-blue-50/30'
                                    }`}
                            >
                                {selectedFile ? (
                                    <div className="flex flex-col items-center gap-2">
                                        <div className="w-12 h-12 rounded-xl bg-red-50 flex items-center justify-center">
                                            <FileText size={24} className="text-red-400" />
                                        </div>
                                        <p className="text-sm font-medium text-slate-700">{selectedFile.name}</p>
                                        <p className="text-xs text-slate-400">{formatFileSize(selectedFile.size)}</p>
                                    </div>
                                ) : (
                                    <div className="flex flex-col items-center gap-2">
                                        <div className="w-12 h-12 rounded-xl bg-slate-100 flex items-center justify-center">
                                            <Upload size={24} className="text-slate-400" />
                                        </div>
                                        <p className="text-sm text-slate-600">点击选择 PDF 文件</p>
                                        <p className="text-xs text-slate-400">支持 .pdf 格式</p>
                                    </div>
                                )}
                                <input
                                    ref={fileInputRef}
                                    type="file"
                                    accept=".pdf"
                                    onChange={handleFileSelect}
                                    className="hidden"
                                />
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-xs font-medium text-slate-500 mb-1.5">Chunk Size</label>
                                    <input
                                        type="number"
                                        value={chunkSize}
                                        onChange={(e) => setChunkSize(Number(e.target.value))}
                                        className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none text-sm"
                                    />
                                </div>
                                <div>
                                    <label className="block text-xs font-medium text-slate-500 mb-1.5">Chunk Overlap</label>
                                    <input
                                        type="number"
                                        value={chunkOverlap}
                                        onChange={(e) => setChunkOverlap(Number(e.target.value))}
                                        className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none text-sm"
                                    />
                                </div>
                            </div>
                        </div>
                        <div className="p-4 bg-slate-50 rounded-b-2xl flex justify-end gap-3 border-t border-slate-100">
                            <button
                                onClick={() => { setShowImportModal(false); setSelectedFile(null); }}
                                className="px-4 py-2 text-sm text-slate-600 hover:bg-slate-200 rounded-lg transition-colors"
                            >
                                取消
                            </button>
                            <button
                                onClick={handleUpload}
                                disabled={!selectedFile}
                                className="px-5 py-2 text-sm bg-gradient-to-r from-blue-500 to-blue-600 text-white rounded-lg hover:from-blue-600 hover:to-blue-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-sm font-medium"
                            >
                                开始导入
                            </button>
                        </div>
                    </div>
                </>
            )}


        </div>
    );
}
