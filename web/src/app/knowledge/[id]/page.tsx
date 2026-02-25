'use client';

import { useEffect, useState, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useAppContext } from '@/context/AppContext';
import { ArrowLeft, Upload, Trash2, X } from 'lucide-react';

interface KBDetail {
    id: string;
    name: string;
    description?: string;
    embedding_model: string;
    files: FileInfo[];
}

interface FileInfo {
    id: string;
    name: string;
    size: number;
    chunks: number;
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
    const [uploading, setUploading] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);

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

    const handleUpload = async () => {
        if (!selectedFile) return;
        setUploading(true);
        try {
            const formData = new FormData();
            formData.append('file', selectedFile);
            formData.append('chunk_size', String(chunkSize));
            formData.append('chunk_overlap', String(chunkOverlap));

            const res = await fetch(`/api/kbs/${kbId}/ingest`, {
                method: 'POST',
                body: formData,
            });
            const data = await res.json();
            if (data.success) {
                setShowImportModal(false);
                setSelectedFile(null);
                fetchKbDetail();
                refreshKbs();
            } else {
                alert(`导入失败: ${data.error}`);
            }
        } catch (e) {
            console.error(e);
            alert('导入失败');
        } finally {
            setUploading(false);
        }
    };

    const handleDeleteFile = async (fileId: string) => {
        if (!confirm('确定要移除这个文档吗？')) return;
        try {
            await fetch(`/api/kbs/${kbId}/files/${fileId}`, { method: 'DELETE' });
            fetchKbDetail();
            refreshKbs();
        } catch (e) {
            console.error(e);
        }
    };

    if (loading) {
        return <div className="p-8 text-slate-500">加载中...</div>;
    }

    if (!kb) {
        return <div className="p-8 text-slate-500">知识库不存在</div>;
    }

    return (
        <div className="h-full flex flex-col">
            {/* Header */}
            <header className="h-18 px-8 flex items-center justify-between bg-white border-b border-slate-200">
                <div className="flex items-center gap-4">
                    <button
                        onClick={() => router.push('/knowledge')}
                        className="p-2 rounded-lg hover:bg-slate-100 text-slate-600"
                    >
                        <ArrowLeft size={20} />
                    </button>
                    <h1 className="text-xl font-semibold text-slate-800">{kb.name}</h1>
                    <span className="px-2 py-1 bg-slate-100 text-slate-600 text-xs rounded-full">
                        {kb.embedding_model.split('/').pop()}
                    </span>
                </div>
                <button
                    onClick={() => setShowImportModal(true)}
                    className="flex items-center gap-2 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors shadow-sm"
                >
                    <Upload size={18} />
                    导入文档
                </button>
            </header>

            {/* Content */}
            <div className="flex-1 p-8 overflow-y-auto">
                <div className="mb-4">
                    <h2 className="text-lg font-semibold text-slate-700">已导入文档</h2>
                </div>
                <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
                    <table className="w-full">
                        <thead className="bg-slate-50">
                            <tr>
                                <th className="text-left px-6 py-3 text-xs font-semibold text-slate-500 uppercase">文件名</th>
                                <th className="text-left px-6 py-3 text-xs font-semibold text-slate-500 uppercase">大小</th>
                                <th className="text-left px-6 py-3 text-xs font-semibold text-slate-500 uppercase">导入时间</th>
                                <th className="text-left px-6 py-3 text-xs font-semibold text-slate-500 uppercase">Chunk数</th>
                                <th className="text-left px-6 py-3 text-xs font-semibold text-slate-500 uppercase">操作</th>
                            </tr>
                        </thead>
                        <tbody>
                            {kb.files.length === 0 ? (
                                <tr>
                                    <td colSpan={5} className="text-center py-12 text-slate-400">
                                        暂无文档，请点击右上角导入
                                    </td>
                                </tr>
                            ) : (
                                kb.files.map((file) => (
                                    <tr key={file.id} className="border-t border-slate-100 hover:bg-slate-50">
                                        <td className="px-6 py-4 text-slate-800">{file.name}</td>
                                        <td className="px-6 py-4 text-slate-600">{(file.size / 1024).toFixed(1)} KB</td>
                                        <td className="px-6 py-4 text-slate-600">{new Date(file.uploaded_at).toLocaleString()}</td>
                                        <td className="px-6 py-4 text-slate-600">{file.chunks}</td>
                                        <td className="px-6 py-4">
                                            <button
                                                onClick={() => handleDeleteFile(file.id)}
                                                className="p-2 rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-50"
                                            >
                                                <Trash2 size={16} />
                                            </button>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* Import Modal */}
            {showImportModal && (
                <>
                    <div className="fixed inset-0 bg-black/40 z-40" onClick={() => setShowImportModal(false)} />
                    <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white rounded-xl shadow-xl w-full max-w-md z-50">
                        <div className="p-6 border-b border-slate-200 flex justify-between items-center">
                            <h3 className="text-lg font-semibold">导入文档</h3>
                            <button onClick={() => setShowImportModal(false)} className="text-slate-400 hover:text-slate-600">
                                <X size={20} />
                            </button>
                        </div>
                        <div className="p-6 space-y-4">
                            <div
                                onClick={() => fileInputRef.current?.click()}
                                className="border-2 border-dashed border-slate-300 rounded-lg p-8 text-center cursor-pointer hover:border-blue-400 hover:bg-blue-50/50 transition-colors"
                            >
                                <Upload className="mx-auto text-slate-400 mb-2" size={32} />
                                <p className="text-slate-600">{selectedFile ? selectedFile.name : '点击选择 PDF 文件'}</p>
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
                                    <label className="block text-sm font-medium text-slate-700 mb-1">Chunk Size</label>
                                    <input
                                        type="number"
                                        value={chunkSize}
                                        onChange={(e) => setChunkSize(Number(e.target.value))}
                                        className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-slate-700 mb-1">Chunk Overlap</label>
                                    <input
                                        type="number"
                                        value={chunkOverlap}
                                        onChange={(e) => setChunkOverlap(Number(e.target.value))}
                                        className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                                    />
                                </div>
                            </div>
                        </div>
                        <div className="p-4 bg-slate-50 rounded-b-xl flex justify-end gap-3">
                            <button
                                onClick={() => setShowImportModal(false)}
                                className="px-4 py-2 text-slate-600 hover:bg-slate-200 rounded-lg transition-colors"
                            >
                                取消
                            </button>
                            <button
                                onClick={handleUpload}
                                disabled={uploading || !selectedFile}
                                className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                {uploading ? '导入中...' : '开始导入'}
                            </button>
                        </div>
                    </div>
                </>
            )}
        </div>
    );
}
