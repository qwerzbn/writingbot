'use client';

import { useState, useRef, useCallback, useEffect } from 'react';
import {
    Eye, Edit3, Columns, Bold, Italic, Heading1, Code, Link2,
    Save, Sigma, BookOpen, Calendar, Wand2, Sparkles, FileText,
    Tags, Loader2, StopCircle
} from 'lucide-react';
import MarkdownRenderer from '@/components/MarkdownRenderer';
import TagInput from './TagInput';

interface NoteData {
    id: string;
    notebook_id: string;
    title: string;
    content: string;
    tags: string[];
    source: {
        type: string;
        file_name?: string;
        page?: number;
        chunk_id?: string;
        original_quote?: string;
        evidence_links?: Array<{ id?: string; source?: string; page?: number | string; content?: string }>;
        citation_count?: number;
        last_used_at?: string;
    };
    created_at: string;
    updated_at: string;
    ai_meta?: {
        summary?: string;
        suggested_tags?: string[];
    };
}

interface NoteEditorProps {
    note: NoteData;
    onSave: (updates: { title?: string; content?: string; tags?: string[]; expected_updated_at: string }) => Promise<string | null>;
    saving?: boolean;
    saveConflict?: string | null;
    onSelectRelated?: (noteId: string, notebookId?: string) => void;
}

type ViewMode = 'edit' | 'preview' | 'split';
type AIAction = 'polish' | 'continue' | 'summarize' | 'suggest_tags' | 'custom' | null;
interface AIActionOptions {
    writeToContent?: boolean;
}
interface RelatedNote {
    id: string;
    notebook_id?: string;
    notebook_name?: string;
    title: string;
    tags: string[];
    score?: number;
}

export default function NoteEditor({ note, onSave, saving, saveConflict, onSelectRelated }: NoteEditorProps) {
    const [title, setTitle] = useState(note.title);
    const [content, setContent] = useState(note.content);
    const [tags, setTags] = useState<string[]>(note.tags);
    const [mode, setMode] = useState<ViewMode>('edit');
    const [hasChanges, setHasChanges] = useState(false);
    
    // AI state
    const [aiAction, setAiAction] = useState<AIAction>(null);
    const [aiError, setAiError] = useState<string | null>(null);
    const [relatedNotes, setRelatedNotes] = useState<RelatedNote[]>([]);
    const [loadingRelated, setLoadingRelated] = useState(false);
    const [highRelevanceOnly, setHighRelevanceOnly] = useState(true);
    const abortControllerRef = useRef<AbortController | null>(null);

    const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const saveVersionRef = useRef(0);
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const updatedAtRef = useRef(note.updated_at);
    const activeNoteIdRef = useRef(note.id);

    // Sync when note changes externally
    useEffect(() => {
        const noteSwitched = activeNoteIdRef.current !== note.id;
        activeNoteIdRef.current = note.id;
        if (noteSwitched) {
            // Invalidate pending saves from previous note to avoid stale callbacks
            saveVersionRef.current += 1;
            if (saveTimerRef.current) {
                clearTimeout(saveTimerRef.current);
                saveTimerRef.current = null;
            }
        }
        setTitle(note.title);
        setContent(note.content);
        setTags(note.tags);
        setHasChanges(false);
        if (noteSwitched) {
            setAiAction(null);
            setAiError(null);
            setRelatedNotes([]);
            setHighRelevanceOnly(true);
            if (abortControllerRef.current) {
                abortControllerRef.current.abort();
                abortControllerRef.current = null;
            }
        }
        updatedAtRef.current = note.updated_at;
    }, [note.id, note.updated_at, note.title, note.content, note.tags]);

    const persistMeta = useCallback(async (updates: { summary?: string; suggested_tags?: string[] }) => {
        try {
            const res = await fetch(`/api/notebooks/${note.notebook_id}/notes/${note.id}/meta`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updates),
            });
            if (!res.ok) {
                const txt = await res.text();
                throw new Error(txt || `Meta update failed (${res.status})`);
            }
        } catch (e) {
            console.error('Failed to persist note meta:', e);
        }
    }, [note.id, note.notebook_id]);

    const fetchRelatedNotes = useCallback(async () => {
        setLoadingRelated(true);
        try {
            const minScore = highRelevanceOnly ? 2.0 : 0.0;
            const res = await fetch(`/api/notebooks/${note.notebook_id}/notes/${note.id}/related?limit=5&include_all=true&min_score=${minScore}`);
            if (!res.ok) {
                setRelatedNotes([]);
                return;
            }
            const data = await res.json();
            if (data.success) {
                setRelatedNotes(data.data || []);
            } else {
                setRelatedNotes([]);
            }
        } catch (e) {
            console.error('Failed to fetch related notes:', e);
            setRelatedNotes([]);
        } finally {
            setLoadingRelated(false);
        }
    }, [note.id, note.notebook_id, highRelevanceOnly]);

    useEffect(() => {
        fetchRelatedNotes();
    }, [fetchRelatedNotes, note.updated_at]);

    useEffect(() => {
        return () => {
            if (saveTimerRef.current) {
                clearTimeout(saveTimerRef.current);
                saveTimerRef.current = null;
            }
            if (abortControllerRef.current) {
                abortControllerRef.current.abort();
                abortControllerRef.current = null;
            }
        };
    }, []);

    const scheduleSave = useCallback(
        (newTitle: string, newContent: string, newTags: string[]) => {
            setHasChanges(true);
            if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
            const saveVersion = ++saveVersionRef.current;
            saveTimerRef.current = setTimeout(async () => {
                const savedUpdatedAt = await onSave({
                    title: newTitle,
                    content: newContent,
                    tags: newTags,
                    expected_updated_at: updatedAtRef.current,
                });

                // Ignore stale save completion from older requests
                if (saveVersion !== saveVersionRef.current) return;

                if (savedUpdatedAt) {
                    setHasChanges(false);
                    updatedAtRef.current = savedUpdatedAt;
                } else {
                    setHasChanges(true);
                }
            }, 1000);
        },
        [onSave],
    );

    const handleTitleChange = (val: string) => {
        setTitle(val);
        scheduleSave(val, content, tags);
    };

    const handleContentChange = (val: string) => {
        setContent(val);
        scheduleSave(title, val, tags);
    };

    const handleTagsChange = (newTags: string[]) => {
        setTags(newTags);
        scheduleSave(title, content, newTags);
    };

    // ---- Toolbar insert helpers ----
    const insertAtCursor = (before: string, after: string = '') => {
        const ta = textareaRef.current;
        if (!ta) return;
        const start = ta.selectionStart;
        const end = ta.selectionEnd;
        const selected = content.substring(start, end);
        const newContent =
            content.substring(0, start) + before + selected + after + content.substring(end);
        handleContentChange(newContent);
        setTimeout(() => {
            ta.focus();
            ta.selectionStart = start + before.length;
            ta.selectionEnd = start + before.length + selected.length;
        }, 0);
    };

    const toolbarItems = [
        { icon: Bold, label: '粗体', action: () => insertAtCursor('**', '**') },
        { icon: Italic, label: '斜体', action: () => insertAtCursor('*', '*') },
        { icon: Heading1, label: '标题', action: () => insertAtCursor('## ') },
        { icon: Code, label: '代码', action: () => insertAtCursor('`', '`') },
        { icon: Link2, label: '链接', action: () => insertAtCursor('[', '](url)') },
        { icon: Sigma, label: '公式', action: () => insertAtCursor('$', '$') },
    ];

    const insertPaperTemplate = () => {
        const template = [
            '## 论文信息',
            '- 标题：',
            '- 作者：',
            '- 来源：',
            '- 年份：',
            '',
            '## 核心问题',
            '- ',
            '',
            '## 方法概览',
            '- ',
            '',
            '## 关键结论',
            '- ',
            '',
            '## 实验与证据',
            '- ',
            '',
            '## 局限性',
            '- ',
            '',
            '## 我的思考',
            '- ',
        ].join('\n');

        if (!content.trim()) {
            handleContentChange(template);
            return;
        }

        insertAtCursor(`\n\n${template}\n`);
    };

    const sourceLabel = () => {
        if (!note.source || note.source.type === 'manual') return null;
        if (note.source.type === 'co_writer') return '✍️ 来自协同写作';
        if (note.source.type === 'research') return '🔬 来自深度研究';
        if (note.source.type === 'knowledge_base')
            return `📚 ${note.source.file_name || '知识库'}${note.source.page ? ` p.${note.source.page}` : ''}`;
        return null;
    };

    // ---- AI Assistant ----

    const stopAi = () => {
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
            abortControllerRef.current = null;
        }
        setAiAction(null);
    };

    const handleAiAction = async (
        action: AIAction,
        instruction: string = '',
        options: AIActionOptions = {},
    ) => {
        if (!content.trim() && action !== 'continue' && action !== 'custom') {
            setAiError('当前笔记为空，请先输入内容后再使用该功能。');
            return;
        }
        setAiError(null);
        const writeToContent = options.writeToContent ?? true;
        
        // Setup abort controller for cancel
        if (abortControllerRef.current) abortControllerRef.current.abort();
        const abortController = new AbortController();
        abortControllerRef.current = abortController;
        
        setAiAction(action);
        let finalContent = content;
        let streamedData = '';
        let streamFailed = false;
        let hasChunk = false;

        // Pre-processing based on action
        if (!writeToContent) {
            finalContent = content;
        } else if (action === 'polish') {
            finalContent = ''; // Will recreate completely
        } else if (action === 'continue') {
            finalContent += '\n\n'; // Append space
        } else if (action === 'summarize') {
            finalContent = '> **AI 摘要**：\n> '; // Prepend space
        } else if (action === 'custom') {
            finalContent = `${content}\n\n---\n\n### AI 论文助手\n`;
        }

        try {
            const response = await fetch('/api/notebooks/ai/stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    action,
                    content: action === 'continue' ? content.slice(-2000) : content, // Only send recent context for continue
                    title,
                    instruction,
                }),
                signal: abortController.signal
            });

            if (!response.ok) {
                const errText = await response.text();
                throw new Error(errText || `API Error (${response.status})`);
            }

            const reader = response.body?.getReader();
            if (!reader) throw new Error('No response body');

            const decoder = new TextDecoder();
            let buffer = '';

            const processData = (dataStr: string) => {
                if (dataStr === '[DONE]' || !dataStr) return;

                let data: { chunk?: string; error?: string };
                try {
                    data = JSON.parse(dataStr) as { chunk?: string; error?: string };
                } catch (e) {
                    console.error('JSON parse error:', e, 'Raw:', dataStr);
                    return;
                }

                if (data.error) {
                    setAiError(data.error);
                    streamFailed = true;
                    return;
                }
                if (!data.chunk) return;

                streamedData += data.chunk;
                hasChunk = true;

                // Live update state based on action
                if (!writeToContent) {
                    return;
                }
                if (action === 'polish') {
                    setContent(streamedData);
                } else if (action === 'continue') {
                    setContent(finalContent + streamedData);
                } else if (action === 'summarize') {
                    const summaryLines = streamedData.split('\n').map((line) => `> ${line}`).join('\n');
                    setContent(`> **AI 摘要**：\n${summaryLines}\n\n${content}`);
                } else if (action === 'custom') {
                    setContent(finalContent + streamedData);
                }
            };

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const events = buffer.split('\n\n');
                buffer = events.pop() || '';

                for (const event of events) {
                    const lines = event.split('\n');
                    for (const line of lines) {
                        if (line.startsWith('data:')) {
                            processData(line.slice(5).trim());
                        }
                    }
                }
            }

            if (buffer.trim()) {
                const lines = buffer.split('\n');
                for (const line of lines) {
                    if (line.startsWith('data:')) {
                        processData(line.slice(5).trim());
                    }
                }
            }

            // Post-processing
            if (streamFailed || !hasChunk) {
                return;
            }
            if (action === 'suggest_tags') {
                const newTagsStr = streamedData.replace(/[\[\]"]/g, '').split(',').map(t => t.trim()).filter(Boolean);
                const mergedTags = Array.from(new Set([...tags, ...newTagsStr])).slice(0, 10);
                setTags(mergedTags);
                scheduleSave(title, content, mergedTags);
                await persistMeta({ suggested_tags: newTagsStr.slice(0, 10) });
            } else {
                if (writeToContent) {
                    // Ensure the final content is saved
                    let newContent = content;
                    if (action === 'polish') newContent = streamedData;
                    else if (action === 'continue') newContent = finalContent + streamedData;
                    else if (action === 'summarize') {
                         const summaryLines = streamedData.split('\n').map(l => '> ' + l).join('\n');
                         newContent = `> **AI 摘要**：\n${summaryLines}\n\n${content}`;
                    } else if (action === 'custom') {
                        newContent = finalContent + streamedData;
                    }
                    setContent(newContent);
                    scheduleSave(title, newContent, tags);
                }
                if (action === 'summarize') {
                    await persistMeta({ summary: streamedData.trim() });
                }
            }

        } catch (e: unknown) {
            if (!(e instanceof Error && e.name === 'AbortError')) {
                console.error('AI Error:', e);
                setAiError(e instanceof Error ? e.message : 'AI 请求失败，请稍后重试。');
            }
        } finally {
            if (abortControllerRef.current === abortController) {
                setAiAction(null);
                abortControllerRef.current = null;
            }
        }
    };

    const hasContent = content.trim().length > 0;

    return (
        <div className="flex flex-col h-full bg-white dark:bg-slate-900 border-l border-slate-200 dark:border-slate-700">
            {/* Header: title + meta */}
            <div className="px-6 pt-5 pb-3 border-b border-slate-200 dark:border-slate-700 space-y-3 shrink-0">
                <input
                    type="text"
                    value={title}
                    onChange={(e) => handleTitleChange(e.target.value)}
                    placeholder="笔记标题"
                    className="w-full text-xl font-bold bg-transparent outline-none text-slate-800 dark:text-white placeholder:text-slate-400"
                />

                {/* Tags */}
                <TagInput tags={tags} onChange={handleTagsChange} />

                {/* Meta row */}
                <div className="flex items-center gap-4 text-xs text-slate-400">
                    {sourceLabel() && (
                        <span className="flex items-center gap-1">
                            {sourceLabel()}
                        </span>
                    )}
                    <span className="flex items-center gap-1">
                        <Calendar size={12} />
                        {new Date(note.updated_at).toLocaleString('zh-CN')}
                    </span>
                    {saving && (
                        <span className="flex items-center gap-1 text-blue-500">
                            <Save size={12} className="animate-pulse" /> 保存中...
                        </span>
                    )}
                    {!saving && hasChanges && <span className="text-amber-500">● 未保存</span>}
                    {!saving && !hasChanges && <span className="text-emerald-500">✓ 已保存</span>}
                </div>
                {saveConflict && (
                    <div className="text-[11px] text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 px-2 py-1 rounded">
                        {saveConflict}
                    </div>
                )}
                {(note.source && ((note.source?.citation_count ?? 0) > 0 || (note.source?.evidence_links?.length ?? 0) > 0 || Boolean(note.source?.type))) && (
                    <div className="text-[11px] rounded border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 px-2 py-2 text-slate-600 dark:text-slate-300 space-y-1">
                        <div className="font-medium text-slate-700 dark:text-slate-200">证据视图</div>
                        <div>
                            引用次数：{note.source?.citation_count ?? 0}
                            {note.source?.last_used_at ? ` · 最近使用：${new Date(note.source.last_used_at).toLocaleString('zh-CN')}` : ''}
                        </div>
                        {(note.source?.evidence_links || []).length > 0 ? (
                            (note.source?.evidence_links || []).slice(0, 3).map((ev, idx) => (
                                <div key={`${ev.id || 'ev'}-${idx}`} className="truncate">
                                    [{idx + 1}] {ev.source || '未知来源'}{ev.page ? ` p.${ev.page}` : ''}
                                </div>
                            ))
                        ) : (
                            <div className="text-slate-400 dark:text-slate-500">当前笔记没有可展示的来源片段。</div>
                        )}
                    </div>
                )}
            </div>

            {/* Toolbar + mode switch */}
            <div className="px-6 py-2 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between bg-slate-50 dark:bg-slate-800/50 shrink-0">
                {/* Formatting Toolbar */}
                <div className="flex items-center gap-1">
                    {toolbarItems.map(({ icon: Icon, label, action }) => (
                        <button
                            key={label}
                            onClick={action}
                            title={label}
                            disabled={mode === 'preview' || Boolean(aiAction)}
                            className="p-1.5 rounded hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-500 dark:text-slate-400 disabled:opacity-30 transition-colors"
                        >
                            <Icon size={15} />
                        </button>
                    ))}
                    <button
                        onClick={insertPaperTemplate}
                        title="插入论文阅读模板"
                        disabled={mode === 'preview' || Boolean(aiAction)}
                        className="ml-1 p-1.5 rounded hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-500 dark:text-slate-400 disabled:opacity-30 transition-colors"
                    >
                        <BookOpen size={15} />
                    </button>
                </div>

                {/* Mode switch */}
                <div className="flex items-center gap-0.5 bg-slate-200 dark:bg-slate-700 rounded-lg p-0.5">
                    {([
                        { key: 'edit' as const, icon: Edit3, label: '编辑' },
                        { key: 'split' as const, icon: Columns, label: '分屏' },
                        { key: 'preview' as const, icon: Eye, label: '预览' },
                    ]).map(({ key, icon: Icon, label }) => (
                        <button
                            key={key}
                            onClick={() => setMode(key)}
                            className={`px-2.5 py-1 rounded-md text-xs font-medium flex items-center gap-1 transition-all ${
                                mode === key
                                    ? 'bg-white dark:bg-slate-600 text-slate-800 dark:text-white shadow-sm'
                                    : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300'
                            }`}
                        >
                            <Icon size={13} />
                            {label}
                        </button>
                    ))}
                </div>
            </div>

            {/* Editor / Preview */}
            <div className="flex-1 overflow-hidden flex relative">
                {/* Edit pane */}
                {(mode === 'edit' || mode === 'split') && (
                    <div className={`${mode === 'split' ? 'w-1/2 border-r border-slate-200 dark:border-slate-700' : 'w-full'} overflow-visible relative h-full flex flex-col`}>
                        <textarea
                            ref={textareaRef}
                            value={content}
                            onChange={(e) => handleContentChange(e.target.value)}
                            disabled={Boolean(aiAction)}
                            placeholder="在这里书写 Markdown 笔记...&#10;&#10;支持 LaTeX: $E=mc^2$&#10;支持代码块、表格等"
                            className="flex-1 w-full p-6 pb-20 bg-transparent outline-none resize-none text-sm text-slate-800 dark:text-slate-200 placeholder:text-slate-400 font-mono leading-relaxed disabled:opacity-80 disabled:cursor-not-allowed"
                        />
                    </div>
                )}

                {/* Preview pane */}
                {(mode === 'preview' || mode === 'split') && (
                    <div className={`${mode === 'split' ? 'w-1/2' : 'w-full'} overflow-auto p-6 pb-20`}>
                        {content ? (
                            <div className="prose dark:prose-invert prose-sm max-w-none">
                                <MarkdownRenderer content={content} />
                            </div>
                        ) : (
                            <div className="flex flex-col items-center justify-center h-full text-slate-400">
                                <BookOpen size={32} className="mb-2 opacity-30" />
                                <p className="text-sm">暂无内容</p>
                            </div>
                        )}
                    </div>
                )}
                
                {/* Loading overlay during AI stream (if needed, currently streaming is live) */}
            </div>

            {/* Related Notes */}
            <div className="px-4 py-2 border-t border-slate-100 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-900/40 shrink-0">
                <div className="flex items-center justify-between mb-1.5">
                    <div className="flex items-center gap-2">
                        <span className="text-[11px] font-medium text-slate-500 dark:text-slate-400">
                            相关笔记
                        </span>
                        <button
                            onClick={() => setHighRelevanceOnly((v) => !v)}
                            className={`px-1.5 py-0.5 rounded text-[10px] border ${
                                highRelevanceOnly
                                    ? 'text-indigo-600 dark:text-indigo-300 border-indigo-200 dark:border-indigo-700 bg-indigo-50 dark:bg-indigo-900/20'
                                    : 'text-slate-500 dark:text-slate-400 border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800'
                            }`}
                        >
                            {highRelevanceOnly ? '高相关' : '全部'}
                        </button>
                    </div>
                    {loadingRelated && (
                        <span className="text-[10px] text-slate-400 flex items-center gap-1">
                            <Loader2 size={10} className="animate-spin" />
                            计算中
                        </span>
                    )}
                </div>
                {relatedNotes.length > 0 ? (
                    <div className="flex flex-wrap gap-1.5">
                        {relatedNotes.map((item) => (
                            <button
                                key={item.id}
                                onClick={() => onSelectRelated?.(item.id, item.notebook_id)}
                                className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-[11px] bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:text-indigo-600 dark:hover:text-indigo-400 hover:border-indigo-300 dark:hover:border-indigo-700 transition-colors"
                                title={`${item.notebook_name ? `${item.notebook_name} · ` : ''}${item.title}`}
                            >
                                <BookOpen size={11} />
                                <span className="max-w-[180px] truncate">{item.title}</span>
                                {item.notebook_name && item.notebook_id !== note.notebook_id && (
                                    <span className="text-[10px] text-slate-400">[{item.notebook_name}]</span>
                                )}
                                {typeof item.score === 'number' && (
                                    <span className="text-[10px] text-slate-400">({item.score.toFixed(1)})</span>
                                )}
                            </button>
                        ))}
                    </div>
                ) : (
                    <p className="text-[11px] text-slate-400">暂无可推荐的相关笔记</p>
                )}
            </div>

            {/* AI Assistant Toolbar (Floating at bottom for edit/split mode or fixed if small) */}
            <div className="px-4 py-2 bg-gradient-to-r from-indigo-50/80 to-purple-50/80 dark:from-indigo-900/20 dark:to-purple-900/20 border-t border-indigo-100 dark:border-indigo-800/30 flex items-center justify-between shrink-0">
                <div className="flex items-center gap-3">
                    <div className="flex items-center gap-1.5 text-indigo-500 font-medium text-xs mr-2">
                        <Wand2 size={14} className={aiAction ? "animate-pulse" : ""} />
                        AI 助手
                    </div>

                    {aiAction ? (
                        <div className="flex items-center gap-3">
                            <span className="text-xs text-indigo-600 dark:text-indigo-400 flex items-center gap-1.5 bg-indigo-100 dark:bg-indigo-900/30 px-2 py-1 rounded">
                                <Loader2 size={12} className="animate-spin" />
                                正在生成中...
                            </span>
                            <button
                                onClick={stopAi}
                                className="flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                            >
                                <StopCircle size={13} /> 中止
                            </button>
                        </div>
                    ) : (
                        <div className="flex items-center gap-1">
                            <button
                                onClick={() => handleAiAction('polish')}
                                disabled={!hasContent}
                                title={hasContent ? '润色全文' : '请先输入笔记内容'}
                                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:text-indigo-600 dark:hover:text-indigo-400 shadow-sm border border-slate-200 dark:border-slate-700 hover:border-indigo-300 dark:hover:border-indigo-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                <Sparkles size={13} /> 润色全文
                            </button>
                            <button
                                onClick={() => handleAiAction('continue')}
                                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:text-indigo-600 dark:hover:text-indigo-400 shadow-sm border border-slate-200 dark:border-slate-700 hover:border-indigo-300 dark:hover:border-indigo-700 transition-all disabled:opacity-50"
                            >
                                <Edit3 size={13} /> AI 续写
                            </button>
                            <button
                                onClick={() => handleAiAction('summarize')}
                                disabled={!hasContent}
                                title={hasContent ? '生成摘要' : '请先输入笔记内容'}
                                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:text-indigo-600 dark:hover:text-indigo-400 shadow-sm border border-slate-200 dark:border-slate-700 hover:border-indigo-300 dark:hover:border-indigo-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                <FileText size={13} /> 生成摘要
                            </button>
                            <button
                                onClick={() => handleAiAction('summarize', '', { writeToContent: false })}
                                disabled={!hasContent}
                                title={hasContent ? '更新摘要卡片' : '请先输入笔记内容'}
                                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:text-indigo-600 dark:hover:text-indigo-400 shadow-sm border border-slate-200 dark:border-slate-700 hover:border-indigo-300 dark:hover:border-indigo-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                <FileText size={13} /> 更新摘要卡片
                            </button>
                            <button
                                onClick={() => handleAiAction('suggest_tags')}
                                disabled={!hasContent}
                                title={hasContent ? '推荐标签' : '请先输入笔记内容'}
                                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:text-indigo-600 dark:hover:text-indigo-400 shadow-sm border border-slate-200 dark:border-slate-700 hover:border-indigo-300 dark:hover:border-indigo-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                <Tags size={13} /> 推荐标签
                            </button>
                            <button
                                onClick={() => handleAiAction(
                                    'custom',
                                    '请将当前内容整理为论文阅读卡片，按“研究问题 / 方法 / 关键发现 / 局限性 / 可复现线索”输出，每部分用 Markdown 小标题。'
                                )}
                                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:text-indigo-600 dark:hover:text-indigo-400 shadow-sm border border-slate-200 dark:border-slate-700 hover:border-indigo-300 dark:hover:border-indigo-700 transition-all"
                            >
                                <FileText size={13} /> 提炼要点
                            </button>
                            <button
                                onClick={() => handleAiAction(
                                    'custom',
                                    '请基于当前内容提出 5 个高质量批判性思考问题，并给出每个问题对应的简短分析角度。使用 Markdown 列表输出。'
                                )}
                                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:text-indigo-600 dark:hover:text-indigo-400 shadow-sm border border-slate-200 dark:border-slate-700 hover:border-indigo-300 dark:hover:border-indigo-700 transition-all"
                            >
                                <Sparkles size={13} /> 批判问题
                            </button>
                        </div>
                    )}
                </div>
                {aiError && (
                    <div className="text-[11px] text-red-500 dark:text-red-400 truncate max-w-[45%]" title={aiError}>
                        {aiError}
                    </div>
                )}
                {/* Optional Custom Input for future */}
            </div>
        </div>
    );
}

export type { NoteData };
