'use client';

import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import dynamic from 'next/dynamic';
import { Bot, BookOpen, Copy, Ellipsis, Loader2, PencilLine, Save, Trash2, Upload, X } from 'lucide-react';
import { toast } from 'sonner';

import MarkdownRenderer from '@/components/MarkdownRenderer';
import EvidenceCard from '@/components/common/EvidenceCard';
import { cleanEvidenceTitle, type EvidenceHighlight } from '@/components/common/evidence';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useAppContext } from '@/context/AppContext';
import {
  type CreateNotebookSourcePayload,
  type NotebookChatMessage,
  type NotebookChatSessionDetail,
  type NotebookChatSessionSummary,
  type NotebookCitation,
  type NotebookNoteDetail,
  type NotebookSource,
  type NotebookStudioOutput,
  type NotebookWorkspaceData,
  NotebookApiError,
  createNote,
  createNotebookSource,
  deleteNote,
  deleteNotebookSource,
  generateNotebookStudioOutput,
  getNoteDetail,
  getNotebookChatSession,
  getNotebookWorkspace,
  saveNotebookNoteFromSources,
  saveStudioOutputAsNote,
  streamNotebookChat,
  updateNote,
  updateNotebookSource,
} from '@/lib/notebook-api';
import { useNotebookWorkspaceUiStore } from '@/lib/stores/notebook-workspace-ui-store';
import { cn } from '@/lib/utils';
import {
  ChatEmptyState,
  ChatInput,
  ChatShell,
  MobileTabs,
  NOTEBOOK_THEME_STYLES,
  notebookUi,
  NotebookHeader,
  NoteListItem,
  NoteReadingView,
  NotesPanel,
  SourcesPanel,
} from './workspace-ui';

const PdfViewer = dynamic(() => import('@/components/common/PdfViewer'), { ssr: false });

interface NotebookWorkspaceScreenProps {
  notebookId: string;
}

type MobileTab = 'sources' | 'chat' | 'notes';
type SourceKind = CreateNotebookSourcePayload['kind'];
type NoteViewMode = 'read' | 'edit';

const SOURCE_KIND_OPTIONS: Array<{
  kind: SourceKind;
  label: string;
  description: string;
  icon: typeof Upload;
}> = [
  { kind: 'pdf', label: '上传 PDF', description: '把论文、报告或讲义导入为可检索来源。', icon: Upload },
  { kind: 'url', label: '网页链接', description: '抓取网页正文并转成 notebook 内部来源。', icon: Upload },
  { kind: 'text', label: '粘贴文本', description: '把一段正文、采访稿或会议纪要直接放进来源池。', icon: Upload },
  { kind: 'kb_ref', label: '知识库文件', description: '从现有知识库快照一份文件到当前 notebook。', icon: Upload },
];

function formatDateTime(value?: string | null): string {
  if (!value) return '刚刚';
  try {
    return new Intl.DateTimeFormat('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(value));
  } catch {
    return value;
  }
}

function compactTitle(text: string, fallback: string): string {
  const normalized = (text || '').replace(/\s+/g, ' ').trim();
  return normalized.slice(0, 30) || fallback;
}

function citationSources(citations: NotebookCitation[] = []) {
  return citations.map((citation) => ({
    source: citation.source_title,
    page: citation.page ?? citation.locator,
    line_start: citation.line_start,
    line_end: citation.line_end,
    bbox: citation.bbox,
    page_width: citation.page_width,
    page_height: citation.page_height,
    highlight_boxes: citation.highlight_boxes,
    content: citation.excerpt,
    title: citation.title || citation.source_title,
    summary: citation.summary,
    excerpt: citation.excerpt,
    file_id: citation.source_id,
    asset_id: citation.asset_id,
    asset_type: citation.asset_type,
    caption: citation.caption,
    ref_label: citation.ref_label,
    thumbnail_url: citation.thumbnail_url,
    interpretation: citation.interpretation,
    is_primary: citation.is_primary,
    evidence_kind: citation.evidence_kind,
  }));
}

function notebookAnswerModeLabel(mode?: NotebookChatMessage['answer_mode']) {
  if (mode === 'grounded') return 'Grounded';
  if (mode === 'weakly_grounded') return 'Related sources';
  if (mode === 'llm_fallback') return 'LLM fallback';
  return null;
}

function parseTags(value: string): string[] {
  return value
    .split(/[,\n，]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function buildDraftNote(notebookId: string): NotebookNoteDetail {
  return {
    id: '__draft__',
    notebook_id: notebookId,
    title: '',
    content: '',
    kind: 'manual',
    origin: null,
    citations: [],
    source_ids: [],
    tags: [],
    created_at: '',
    updated_at: '',
    source: {
      type: 'manual',
      citation_count: 0,
      evidence_links: [],
    },
  };
}

function parsePageNumber(page: number | string | undefined): number {
  if (typeof page === 'number' && page > 0) return page;
  const raw = String(page || '').trim();
  const matched = raw.match(/(\d+)/);
  return matched ? Number(matched[1]) : 1;
}

export default function NotebookWorkspaceScreen({ notebookId }: NotebookWorkspaceScreenProps) {
  const { kbs } = useAppContext();
  const setRecentNotebookId = useNotebookWorkspaceUiStore((state) => state.setRecentNotebookId);

  const [workspace, setWorkspace] = useState<NotebookWorkspaceData | null>(null);
  const [sources, setSources] = useState<NotebookSource[]>([]);
  const [selectedSourceIds, setSelectedSourceIds] = useState<string[]>([]);
  const [sessions, setSessions] = useState<NotebookChatSessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [activeSession, setActiveSession] = useState<NotebookChatSessionDetail | null>(null);
  const [studioOutputs, setStudioOutputs] = useState<NotebookStudioOutput[]>([]);
  const [activeOutputId, setActiveOutputId] = useState<string | null>(null);
  const [activeNoteId, setActiveNoteId] = useState<string | null>(null);
  const [activeNote, setActiveNote] = useState<NotebookNoteDetail | null>(null);
  const [mobileTab, setMobileTab] = useState<MobileTab>('chat');
  const [composer, setComposer] = useState('');
  const [chatStreaming, setChatStreaming] = useState(false);
  const [loadingWorkspace, setLoadingWorkspace] = useState(true);
  const [loadingSession, setLoadingSession] = useState(false);
  const [loadingNote, setLoadingNote] = useState(false);
  const [sourceDialogOpen, setSourceDialogOpen] = useState(false);
  const [sourceKind, setSourceKind] = useState<SourceKind>('pdf');
  const [sourceTitle, setSourceTitle] = useState('');
  const [sourceUrl, setSourceUrl] = useState('');
  const [sourceText, setSourceText] = useState('');
  const [sourceFile, setSourceFile] = useState<File | null>(null);
  const [sourceKbId, setSourceKbId] = useState('');
  const [sourceKbFileId, setSourceKbFileId] = useState('');
  const sourceFileInputRef = useRef<HTMLInputElement | null>(null);
  const [submittingSource, setSubmittingSource] = useState(false);
  const [reportGenerating, setReportGenerating] = useState(false);
  const [noteSaving, setNoteSaving] = useState(false);
  const [noteDeleting, setNoteDeleting] = useState(false);
  const [noteViewMode, setNoteViewMode] = useState<NoteViewMode>('read');
  const [noteEditor, setNoteEditor] = useState({ title: '', content: '', tags: '' });
  const [activePdf, setActivePdf] = useState<{
    url: string;
    name: string;
    initialPage: number;
    highlightBoxes?: EvidenceHighlight[];
  } | null>(null);

  const selectedKb = useMemo(() => kbs.find((kb) => kb.id === sourceKbId) || null, [kbs, sourceKbId]);
  const notes = workspace?.notes_summary || [];
  const enabledSources = useMemo(() => sources.filter((source) => selectedSourceIds.includes(source.id)), [selectedSourceIds, sources]);
  const allSourcesSelected = sources.length > 0 && sources.every((source) => source.included);

  const loadSession = useCallback(
    async (sessionId: string | null) => {
      if (!sessionId) {
        setActiveSessionId(null);
        setActiveSession(null);
        return;
      }
      setLoadingSession(true);
      try {
        const detail = await getNotebookChatSession(notebookId, sessionId);
        setActiveSessionId(detail.id);
        setActiveSession(detail);
      } catch (error) {
        toast.error(error instanceof Error ? error.message : '加载聊天会话失败');
      } finally {
        setLoadingSession(false);
      }
    },
    [notebookId]
  );

  const loadWorkspace = useCallback(
    async (options?: {
      preferredSessionId?: string | null;
      preferredOutputId?: string | null;
      preferredNoteId?: string | null;
    }) => {
      setLoadingWorkspace(true);
      try {
        const data = await getNotebookWorkspace(notebookId);
        setWorkspace(data);
        setSources(data.sources);
        setSelectedSourceIds(data.ui_defaults.selected_source_ids);
        setSessions(data.recent_sessions);
        setStudioOutputs(data.studio_outputs);
        setRecentNotebookId(notebookId);

        const nextOutputId =
          options?.preferredOutputId && data.studio_outputs.some((output) => output.id === options.preferredOutputId)
            ? options.preferredOutputId
            : data.ui_defaults.active_output_id || data.studio_outputs[0]?.id || null;
        setActiveOutputId(nextOutputId);

        const nextNoteId =
          options?.preferredNoteId && data.notes_summary.some((note) => note.id === options.preferredNoteId)
            ? options.preferredNoteId
            : null;
        setActiveNoteId(nextNoteId);

        const nextSessionId =
          options?.preferredSessionId && data.recent_sessions.some((session) => session.id === options.preferredSessionId)
            ? options.preferredSessionId
            : data.ui_defaults.active_session_id || data.recent_sessions[0]?.id || null;
        await loadSession(nextSessionId);
      } catch (error) {
        toast.error(error instanceof Error ? error.message : '加载 notebook 工作台失败');
      } finally {
        setLoadingWorkspace(false);
      }
    },
    [loadSession, notebookId, setRecentNotebookId]
  );

  useEffect(() => {
    void loadWorkspace();
  }, [loadWorkspace]);

  useEffect(() => {
    if (!sourceKbId && kbs.length > 0) setSourceKbId(kbs[0].id);
  }, [kbs, sourceKbId]);

  useEffect(() => {
    if (!selectedKb) {
      setSourceKbFileId('');
      return;
    }
    const files = selectedKb.files || [];
    if (!sourceKbFileId || !files.some((file) => file.id === sourceKbFileId)) {
      setSourceKbFileId(files[0]?.id || '');
    }
  }, [selectedKb, sourceKbFileId]);

  useEffect(() => {
    if (!activeNoteId) {
      setActiveNote(null);
      setNoteEditor({ title: '', content: '', tags: '' });
      setNoteViewMode('read');
      return;
    }
    if (activeNoteId === '__draft__') {
      const draft = buildDraftNote(notebookId);
      setActiveNote(draft);
      setNoteEditor({ title: '', content: '', tags: '' });
      setNoteViewMode('edit');
      return;
    }
    let cancelled = false;
    setLoadingNote(true);
    getNoteDetail(notebookId, activeNoteId)
      .then((detail) => {
        if (cancelled) return;
        setActiveNote(detail);
        setNoteEditor({
          title: detail.title,
          content: detail.content,
          tags: detail.tags.join(', '),
        });
        setNoteViewMode('read');
      })
      .catch((error) => {
        if (!cancelled) toast.error(error instanceof Error ? error.message : '加载笔记失败');
      })
      .finally(() => {
        if (!cancelled) setLoadingNote(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeNoteId, notebookId]);

  const handleOpenCitation = useCallback(
    (source: Parameters<typeof EvidenceCard>[0]['source']) => {
      if (!source.file_id) return;
      const fileUrl = `/api/notebooks/${notebookId}/sources/${source.file_id}/content`;
      const fallbackHighlight =
        Array.isArray(source.bbox) && source.bbox.length === 4
          ? [
              {
                page: parsePageNumber(source.page),
                bbox: source.bbox,
                line_start: source.line_start,
                line_end: source.line_end,
                page_width: source.page_width,
                page_height: source.page_height,
              },
            ]
          : [];
      const highlightBoxes = (source.highlight_boxes || []).length > 0 ? source.highlight_boxes : fallbackHighlight;
      setActivePdf({
        url: fileUrl,
        name: source.title || cleanEvidenceTitle(source.source),
        initialPage: parsePageNumber(highlightBoxes?.[0]?.page ?? source.page),
        highlightBoxes,
      });
    },
    [notebookId]
  );

  const handleToggleSource = useCallback(
    async (source: NotebookSource) => {
      const targetIncluded = !source.included;
      try {
        const updated = await updateNotebookSource(notebookId, source.id, { included: targetIncluded });
        setSources((prev) => prev.map((item) => (item.id === source.id ? updated : item)));
        setSelectedSourceIds((prev) =>
          targetIncluded ? Array.from(new Set([...prev, source.id])) : prev.filter((id) => id !== source.id)
        );
      } catch (error) {
        toast.error(error instanceof Error ? error.message : '更新来源失败');
      }
    },
    [notebookId]
  );

  const handleToggleAllSources = useCallback(async () => {
    const nextIncluded = !allSourcesSelected;
    const changedSources = sources.filter((source) => source.included !== nextIncluded);
    try {
      const updated = await Promise.all(
        changedSources.map((source) => updateNotebookSource(notebookId, source.id, { included: nextIncluded }))
      );
      const updatedMap = new Map(updated.map((item) => [item.id, item]));
      setSources((prev) => prev.map((source) => updatedMap.get(source.id) || source));
      setSelectedSourceIds(nextIncluded ? sources.map((source) => source.id) : []);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '批量更新来源失败');
    }
  }, [allSourcesSelected, notebookId, sources]);

  const handleDeleteSource = useCallback(
    async (sourceId: string) => {
      try {
        await deleteNotebookSource(notebookId, sourceId);
        setSources((prev) => prev.filter((source) => source.id !== sourceId));
        setSelectedSourceIds((prev) => prev.filter((id) => id !== sourceId));
        toast.success('来源已删除');
      } catch (error) {
        toast.error(error instanceof Error ? error.message : '删除来源失败');
      }
    },
    [notebookId]
  );

  const resetSourceForm = useCallback(() => {
    setSourceTitle('');
    setSourceUrl('');
    setSourceText('');
    setSourceFile(null);
  }, []);

  const handleCreateSource = useCallback(async () => {
    let payload: CreateNotebookSourcePayload | null = null;
    if (sourceKind === 'pdf') {
      if (!sourceFile) return toast.error('请先选择一个 PDF 文件');
      payload = { kind: 'pdf', title: sourceTitle || undefined, file: sourceFile };
    } else if (sourceKind === 'url') {
      if (!sourceUrl.trim()) return toast.error('请填写网页 URL');
      payload = { kind: 'url', title: sourceTitle || undefined, url: sourceUrl.trim() };
    } else if (sourceKind === 'text') {
      if (!sourceText.trim()) return toast.error('请粘贴要导入的文本内容');
      payload = { kind: 'text', title: sourceTitle || undefined, text: sourceText.trim() };
    } else if (sourceKind === 'kb_ref') {
      if (!sourceKbId || !sourceKbFileId) return toast.error('请选择知识库和文件');
      payload = { kind: 'kb_ref', title: sourceTitle || undefined, kb_id: sourceKbId, file_id: sourceKbFileId };
    }
    if (!payload) return;
    setSubmittingSource(true);
    try {
      const source = await createNotebookSource(notebookId, payload);
      setSources((prev) => [source, ...prev]);
      setSelectedSourceIds((prev) => Array.from(new Set([source.id, ...prev])));
      setSourceDialogOpen(false);
      resetSourceForm();
      toast.success('来源已加入 notebook');
      await loadWorkspace({
        preferredSessionId: activeSessionId,
        preferredOutputId: activeOutputId,
        preferredNoteId: activeNoteId,
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '创建来源失败');
    } finally {
      setSubmittingSource(false);
    }
  }, [
    activeNoteId,
    activeOutputId,
    activeSessionId,
    loadWorkspace,
    notebookId,
    resetSourceForm,
    sourceFile,
    sourceKbFileId,
    sourceKbId,
    sourceKind,
    sourceText,
    sourceTitle,
    sourceUrl,
  ]);

  const handleSend = useCallback(async () => {
    const message = composer.trim();
    if (!message || chatStreaming) return;
    const now = new Date().toISOString();
    const userMessage: NotebookChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: message,
      source_ids: selectedSourceIds,
      created_at: now,
    };
    const placeholderAssistant: NotebookChatMessage = {
      id: `assistant-${Date.now()}`,
      role: 'assistant',
      content: '',
      citations: [],
      source_ids: selectedSourceIds,
      created_at: now,
    };

    setComposer('');
    setChatStreaming(true);
    setActiveSession((prev) =>
      prev
        ? { ...prev, messages: [...prev.messages, userMessage, placeholderAssistant], updated_at: now }
        : {
            id: '__pending__',
            notebook_id: notebookId,
            title: compactTitle(message, 'New chat'),
            messages: [userMessage, placeholderAssistant],
            created_at: now,
            updated_at: now,
          }
    );

    try {
      const result = await streamNotebookChat(
        notebookId,
        {
          session_id: activeSessionId && activeSessionId !== '__pending__' ? activeSessionId : null,
          message,
          source_ids: selectedSourceIds,
        },
        {
          onChunk: (chunk) => {
            setActiveSession((prev) => {
              if (!prev) return prev;
              const messages = [...prev.messages];
              const last = messages[messages.length - 1];
              if (last?.role === 'assistant') messages[messages.length - 1] = { ...last, content: `${last.content || ''}${chunk}` };
              return { ...prev, messages };
            });
          },
          onCitations: (citations) => {
            setActiveSession((prev) => {
              if (!prev) return prev;
              const messages = [...prev.messages];
              const last = messages[messages.length - 1];
              if (last?.role === 'assistant') messages[messages.length - 1] = { ...last, citations };
              return { ...prev, messages };
            });
          },
          onBackgroundExtension: (content) => {
            setActiveSession((prev) => {
              if (!prev) return prev;
              const messages = [...prev.messages];
              const last = messages[messages.length - 1];
              if (last?.role === 'assistant') messages[messages.length - 1] = { ...last, background_extension: content };
              return { ...prev, messages };
            });
          },
        }
      );
      setActiveSessionId(result.session.id);
      setActiveSession(result.session);
      await loadWorkspace({
        preferredSessionId: result.session.id,
        preferredOutputId: activeOutputId,
        preferredNoteId: activeNoteId,
      });
    } catch (error) {
      if (error instanceof NotebookApiError) toast.error(error.message);
      else toast.error(error instanceof Error ? error.message : '发送消息失败');
      await loadSession(activeSessionId);
    } finally {
      setChatStreaming(false);
    }
  }, [
    activeNoteId,
    activeOutputId,
    activeSessionId,
    chatStreaming,
    composer,
    loadSession,
    loadWorkspace,
    notebookId,
    selectedSourceIds,
  ]);

  const handleGenerateReport = useCallback(async () => {
    setReportGenerating(true);
    try {
      const output = await generateNotebookStudioOutput(notebookId, {
        kind: 'summary',
        source_ids: selectedSourceIds,
        session_id: activeSessionId,
      });
      setStudioOutputs((prev) => [output, ...prev.filter((item) => item.id !== output.id)]);
      setActiveOutputId(output.id);
      const note = await saveStudioOutputAsNote(notebookId, output.id);
      toast.success('报告已生成并保存到笔记');
      setActiveNoteId(note.id);
      setNoteViewMode('read');
      await loadWorkspace({
        preferredSessionId: activeSessionId,
        preferredOutputId: output.id,
        preferredNoteId: note.id,
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '生成报告失败');
    } finally {
      setReportGenerating(false);
    }
  }, [activeSessionId, loadWorkspace, notebookId, selectedSourceIds]);

  const handleSaveAssistantAsNote = useCallback(
    async (message: NotebookChatMessage) => {
      try {
        const note = await saveNotebookNoteFromSources(notebookId, {
          title: `聊天笔记：${compactTitle(message.content, 'Notebook chat')}`,
          content: message.background_extension
            ? `${message.content}\n\n## 背景补充\n${message.background_extension}`
            : message.content,
          sources: (message.citations || []).map((citation) => ({
            source_id: citation.source_id,
            source_title: citation.source_title,
            locator: citation.locator,
            excerpt: citation.excerpt,
          })),
          origin_type: 'chat',
          tags: ['chat'],
        });
        toast.success('聊天回复已保存为笔记');
        setActiveNoteId(note.id);
        setNoteViewMode('read');
        await loadWorkspace({
          preferredSessionId: activeSessionId,
          preferredOutputId: activeOutputId,
          preferredNoteId: note.id,
        });
      } catch (error) {
        toast.error(error instanceof Error ? error.message : '保存聊天笔记失败');
      }
    },
    [activeOutputId, activeSessionId, loadWorkspace, notebookId]
  );

  const openNewNote = useCallback(() => {
    setActiveNoteId('__draft__');
    setActiveNote(buildDraftNote(notebookId));
    setNoteEditor({ title: '', content: '', tags: '' });
    setNoteViewMode('edit');
    setMobileTab('notes');
  }, [notebookId]);

  const handleSaveNote = useCallback(async () => {
    if (!activeNote) return;
    const title = noteEditor.title.trim();
    if (!title) return toast.error('请先填写笔记标题');
    setNoteSaving(true);
    try {
      const payload = { title, content: noteEditor.content, tags: parseTags(noteEditor.tags) };
      const saved =
        activeNote.id === '__draft__'
          ? await createNote(notebookId, { ...payload, kind: 'manual', source: { type: 'manual' } })
          : await updateNote(notebookId, activeNote.id, payload);
      setActiveNote(saved);
      setActiveNoteId(saved.id);
      setNoteViewMode('read');
      toast.success('笔记已保存');
      await loadWorkspace({
        preferredSessionId: activeSessionId,
        preferredOutputId: activeOutputId,
        preferredNoteId: saved.id,
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '保存笔记失败');
    } finally {
      setNoteSaving(false);
    }
  }, [activeNote, activeOutputId, activeSessionId, loadWorkspace, noteEditor.content, noteEditor.tags, noteEditor.title, notebookId]);

  const handleDeleteNote = useCallback(async () => {
    if (!activeNote || activeNote.id === '__draft__') return;
    setNoteDeleting(true);
    try {
      await deleteNote(notebookId, activeNote.id);
      const nextId = notes.find((note) => note.id !== activeNote.id)?.id || null;
      setActiveNoteId(nextId);
      if (!nextId) {
        setActiveNote(null);
        setNoteEditor({ title: '', content: '', tags: '' });
      }
      setNoteViewMode('read');
      toast.success('笔记已删除');
      await loadWorkspace({
        preferredSessionId: activeSessionId,
        preferredOutputId: activeOutputId,
        preferredNoteId: nextId,
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '删除笔记失败');
    } finally {
      setNoteDeleting(false);
    }
  }, [activeNote, activeOutputId, activeSessionId, loadWorkspace, notebookId, notes]);

  const handleComposerKeyDown = useCallback(
    (event: KeyboardEvent<HTMLTextAreaElement>) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        void handleSend();
      }
    },
    [handleSend]
  );

  if (loadingWorkspace && !workspace) {
    return (
      <div className="flex h-full min-h-screen items-center justify-center bg-[var(--nb-page-bg)]" style={NOTEBOOK_THEME_STYLES}>
        <div className="flex items-center gap-3 rounded-full border border-[var(--nb-border)] bg-[var(--nb-surface)] px-4 py-2.5 text-[13px] text-[var(--nb-text)]">
          <Loader2 className="h-4 w-4 animate-spin" />
          正在准备智能笔记本工作台
        </div>
      </div>
    );
  }

  if (!workspace) {
    return (
      <div className="flex h-full min-h-screen items-center justify-center bg-[var(--nb-page-bg)]" style={NOTEBOOK_THEME_STYLES}>
        <div className="rounded-[var(--nb-panel-radius)] border border-[var(--nb-border)] bg-[var(--nb-surface)] px-8 py-9 text-center">
          <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-[16px] border border-[var(--nb-border-soft)] bg-[var(--nb-surface-muted)] text-[var(--nb-text-strong)]">
            <BookOpen className="h-6 w-6" />
          </div>
          <div className="mt-4 text-[19px] font-medium text-[var(--nb-text-strong)]">Notebook 不存在</div>
          <p className="mt-2 text-[14px] leading-6 text-[var(--nb-text)]">你可以返回入口页重新创建一个新的智能笔记本。</p>
        </div>
      </div>
    );
  }

  const chatBody = (
    <ScrollArea className="h-full px-5 py-5">
      {loadingSession ? (
        <div className="flex h-full items-center justify-center text-[13px] text-[var(--nb-text)]">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          正在加载对话
        </div>
      ) : activeSession?.messages.length ? (
        <div className="space-y-4">
          {activeSession.messages.map((message) => {
            const isAssistant = message.role === 'assistant';
            return (
              <div
                key={message.id}
                className={cn(
                  'rounded-[20px] border px-5 py-4',
                  isAssistant ? 'border-[var(--nb-border)] bg-[var(--nb-surface)]' : 'ml-auto max-w-[88%] border-[#E3E8F0] bg-[#F6F8FB]'
                )}
              >
                {isAssistant ? (
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2 text-[13px] font-medium text-[var(--nb-text-strong)]">
                      <div className="flex h-9 w-9 items-center justify-center rounded-[14px] border border-[var(--nb-border-soft)] bg-[var(--nb-surface-muted)] text-[var(--nb-text-strong)]">
                        <Bot className="h-4 w-4" />
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span>Notebook Assistant</span>
                        {notebookAnswerModeLabel(message.answer_mode) ? (
                          <span
                            className="rounded-full border border-[var(--nb-border)] bg-[var(--nb-surface-muted)] px-2.5 py-0.5 text-[11px] font-medium text-[var(--nb-text)]"
                            data-testid="chat-answer-mode"
                          >
                            {notebookAnswerModeLabel(message.answer_mode)}
                          </span>
                        ) : null}
                      </div>
                    </div>
                    <div className="text-[12px] text-[var(--nb-text-soft)]">{formatDateTime(message.created_at)}</div>
                  </div>
                ) : null}

                {isAssistant ? (
                  <MarkdownRenderer
                    className="max-w-none text-[var(--nb-text-strong)] prose prose-slate prose-headings:mb-3 prose-headings:text-[var(--nb-text-strong)] prose-p:text-[14px] prose-p:leading-7 prose-p:text-[var(--nb-text-strong)] prose-li:text-[14px] prose-li:leading-7 prose-li:text-[var(--nb-text-strong)] prose-strong:text-[var(--nb-text-strong)] prose-em:text-[var(--nb-text-strong)]"
                    content={message.content || (chatStreaming ? '正在组织答案…' : '')}
                    sources={citationSources(message.citations || [])}
                  />
                ) : (
                  <div className="whitespace-pre-wrap text-[14px] leading-7 text-[var(--nb-text-strong)]">{message.content}</div>
                )}

                {isAssistant && message.background_extension ? (
                  <div className="mt-4 rounded-[18px] border border-[#F1E0B2] bg-[#FFF8E7] px-4 py-3 text-[13px] leading-6 text-[#8A6520]">
                    <div className="mb-1 font-medium">背景补充</div>
                    <div className="whitespace-pre-wrap">{message.background_extension}</div>
                  </div>
                ) : null}

                {isAssistant && (message.citations || []).length > 0 ? (
                  <div className="mt-4 rounded-[18px] border border-[var(--nb-border-soft)] bg-[var(--nb-surface-muted)] px-4 py-3">
                    <div className="mb-2 text-[11px] font-medium uppercase tracking-[0.22em] text-[var(--nb-text-soft)]">Citations</div>
                    <div className="space-y-2">
                      {(message.citations || []).map((citation) => (
                        <EvidenceCard
                          key={`${message.id}:${citation.index}`}
                          index={citation.index}
                          compact
                          source={{
                            source: citation.source_title,
                            page: citation.page ?? citation.locator,
                            line_start: citation.line_start,
                            line_end: citation.line_end,
                            bbox: citation.bbox,
                            page_width: citation.page_width,
                            page_height: citation.page_height,
                            highlight_boxes: citation.highlight_boxes,
                            content: citation.excerpt,
                            title: citation.title || citation.source_title,
                            summary: citation.summary,
                            excerpt: citation.excerpt,
                            file_id: citation.source_id,
                            asset_id: citation.asset_id,
                            asset_type: citation.asset_type,
                            caption: citation.caption,
                            ref_label: citation.ref_label,
                            thumbnail_url: citation.thumbnail_url,
                            interpretation: citation.interpretation,
                            is_primary: citation.is_primary,
                            evidence_kind: citation.evidence_kind,
                          }}
                          onOpen={
                            citation.source_id &&
                            (typeof citation.page === 'number' ||
                              (Array.isArray(citation.highlight_boxes) && citation.highlight_boxes.length > 0) ||
                              (Array.isArray(citation.bbox) && citation.bbox.length === 4))
                              ? handleOpenCitation
                              : undefined
                          }
                        />
                      ))}
                    </div>
                  </div>
                ) : isAssistant ? (
                  <div className="mt-4 rounded-[18px] border border-[var(--nb-border-soft)] bg-[var(--nb-surface-muted)] px-4 py-3 text-[13px] leading-6 text-[var(--nb-text)]">
                    <div className="font-medium text-[var(--nb-text-strong)]">未引用来源</div>
                    <div className="mt-1">
                      {message.answer_mode === 'llm_fallback'
                        ? '当前未选择可引用来源，这条回答基于通用模型知识整理。'
                        : message.answer_mode === 'weakly_grounded'
                          ? '当前回答基于已选来源的相关材料整理，但这次没有形成可直接引用的证据片段。'
                          : '当前回答没有返回可展示的引用片段。'}
                    </div>
                  </div>
                ) : null}

                {isAssistant ? (
                  <div className="mt-4 flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      className={cn(notebookUi.headerButton, 'h-9 px-3')}
                      onClick={() => void handleSaveAssistantAsNote(message)}
                    >
                      <Save className="h-4 w-4" />
                      保存为笔记
                    </Button>
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : (
        <ChatEmptyState
          notebookName={workspace.notebook.name}
          sourceCount={sources.length}
          description={workspace.notebook.description}
          prompts={['帮我快速总结这些来源', '提炼这批资料的关键概念', '把它整理成可复习的问题集']}
          onPromptClick={setComposer}
        />
      )}
    </ScrollArea>
  );

  const notesList = (
    <div className="space-y-2">
      {notes.length === 0 ? (
        <div className="rounded-[18px] border border-dashed border-[var(--nb-border-soft)] bg-[var(--nb-surface)] px-4 py-6 text-center text-[13px] text-[var(--nb-text)]">
          这里还没有保存的笔记。
        </div>
      ) : (
        notes.map((note) => (
          <NoteListItem
            key={note.id}
            note={note}
            active={activeNoteId === note.id}
            onClick={() => {
              setActiveNoteId(note.id);
              setNoteViewMode('read');
            }}
          />
        ))
      )}
    </div>
  );

  const noteDetailHeader = loadingNote ? (
    <div className="text-[13px] text-[var(--nb-text)]">正在加载笔记</div>
  ) : activeNote ? (
    <div className="flex items-center justify-end gap-2">
      {noteViewMode === 'read' && activeNote.id !== '__draft__' ? (
        <span className="mr-auto text-[13px] font-medium text-[var(--nb-text-soft)]" data-testid="note-view-mode-label">
          Report
        </span>
      ) : null}
      <div className="flex items-center gap-2">
        {noteViewMode === 'read' && activeNote.id !== '__draft__' ? (
          <button
            type="button"
            className="inline-flex h-10 items-center gap-2 rounded-[14px] border border-[var(--nb-border)] bg-[var(--nb-surface)] px-3 text-[13px] font-medium text-[var(--nb-text-strong)] transition-colors hover:bg-[var(--nb-surface-muted)]"
            onClick={() => setNoteViewMode('edit')}
            data-testid="note-edit-button"
          >
            <PencilLine className="h-4 w-4" />
            编辑
          </button>
        ) : null}
        {noteViewMode === 'edit' && activeNote.id !== '__draft__' ? (
          <Button
            size="sm"
            variant="ghost"
            className="h-10 rounded-[14px] px-3 text-[13px] text-[var(--nb-text-soft)] hover:bg-[var(--nb-surface-muted)] hover:text-[var(--nb-text-strong)]"
            onClick={() => void handleDeleteNote()}
            disabled={noteDeleting}
          >
            {noteDeleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
            删除
          </Button>
        ) : null}
        {noteViewMode === 'edit' ? (
          <Button
            className={cn(notebookUi.primaryButton, 'h-10')}
            onClick={() => void handleSaveNote()}
            disabled={noteSaving}
            data-testid="note-save-button"
          >
            {noteSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            保存
          </Button>
        ) : (
          <span
            aria-hidden="true"
            className="inline-flex h-10 w-10 items-center justify-center rounded-[14px] text-[var(--nb-text-soft)]"
          >
            <Copy className="h-4 w-4" />
          </span>
        )}
      </div>
    </div>
  ) : (
    <div className="text-[13px] text-[var(--nb-text)]">选择一条笔记开始阅读。</div>
  );

  const noteDetailBody = loadingNote ? (
    <div className="flex h-full items-center justify-center text-[13px] text-[var(--nb-text)]">
      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
      正在加载笔记
    </div>
  ) : activeNote ? (
    noteViewMode === 'read' && activeNote.id !== '__draft__' ? (
      <div className="space-y-5">
        <NoteReadingView activeNote={activeNote} formatDateTime={formatDateTime}>
          {activeNote.citations.length > 0 ? (
            <div className="rounded-[18px] border border-[var(--nb-border)] bg-[var(--nb-surface-muted)] px-4 py-4">
              <div className="mb-3 text-[14px] font-semibold text-[var(--nb-text-strong)]">关联引用</div>
              <div className="space-y-3">
                {activeNote.citations.map((citation) => (
                  <EvidenceCard
                    key={`${activeNote.id}:${citation.index}`}
                    index={citation.index}
                    source={{
                      source: citation.source_title,
                      page: citation.page ?? citation.locator,
                      line_start: citation.line_start,
                      line_end: citation.line_end,
                      bbox: citation.bbox,
                      page_width: citation.page_width,
                      page_height: citation.page_height,
                      highlight_boxes: citation.highlight_boxes,
                      content: citation.excerpt,
                      title: citation.title || citation.source_title,
                      summary: citation.summary,
                      excerpt: citation.excerpt,
                      file_id: citation.source_id,
                      asset_id: citation.asset_id,
                      asset_type: citation.asset_type,
                      caption: citation.caption,
                      ref_label: citation.ref_label,
                      thumbnail_url: citation.thumbnail_url,
                      interpretation: citation.interpretation,
                      is_primary: citation.is_primary,
                      evidence_kind: citation.evidence_kind,
                    }}
                    onOpen={citation.source_id ? handleOpenCitation : undefined}
                  />
                ))}
              </div>
            </div>
          ) : null}
        </NoteReadingView>
      </div>
    ) : (
      <div
        data-testid="note-editor-form"
        className={cn('space-y-4', noteViewMode !== 'edit' && 'hidden')}
      >
        <div>
          <label className="mb-2 block text-[13px] font-medium text-[var(--nb-text-strong)]">标题</label>
          <input
            value={noteEditor.title}
            onChange={(event) => setNoteEditor((prev) => ({ ...prev, title: event.target.value }))}
            className="h-12 w-full rounded-[18px] border border-[var(--nb-border)] bg-[var(--nb-surface-muted)] px-4 text-[14px] text-[var(--nb-text-strong)] outline-none"
            data-testid="note-title-input"
          />
        </div>
        <div>
          <label className="mb-2 block text-[13px] font-medium text-[var(--nb-text-strong)]">标签</label>
          <input
            value={noteEditor.tags}
            onChange={(event) => setNoteEditor((prev) => ({ ...prev, tags: event.target.value }))}
            className="h-12 w-full rounded-[18px] border border-[var(--nb-border)] bg-[var(--nb-surface-muted)] px-4 text-[14px] text-[var(--nb-text-strong)] outline-none"
          />
        </div>
        <div>
          <label className="mb-2 block text-[13px] font-medium text-[var(--nb-text-strong)]">内容</label>
          <textarea
            value={noteEditor.content}
            onChange={(event) => setNoteEditor((prev) => ({ ...prev, content: event.target.value }))}
            className="min-h-[260px] w-full rounded-[18px] border border-[var(--nb-border)] bg-[var(--nb-surface-muted)] px-4 py-3 text-[14px] leading-7 text-[var(--nb-text-strong)] outline-none"
          />
        </div>
      </div>
    )
  ) : (
    <div className="flex h-full items-center justify-center rounded-[18px] border border-dashed border-[var(--nb-border-soft)] bg-[var(--nb-surface-muted)] text-[13px] text-[var(--nb-text)]">
      选择一条笔记开始阅读。
    </div>
  );

  return (
    <>
      <div data-testid="notebook-page-root" style={NOTEBOOK_THEME_STYLES} className={notebookUi.page}>
        <div className={notebookUi.pageWrap}>
          <NotebookHeader
            title={workspace.notebook.name}
            sourceCount={sources.length}
            noteCount={notes.length}
            onAddSource={() => setSourceDialogOpen(true)}
            onAddNote={openNewNote}
          />

          <MobileTabs mobileTab={mobileTab} setMobileTab={setMobileTab} />

          <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[260px_minmax(0,1fr)_minmax(320px,1fr)] xl:grid-cols-[280px_minmax(0,1fr)_minmax(400px,1.2fr)]">
            <SourcesPanel
              sources={sources}
              selectedCount={selectedSourceIds.length}
              allSelected={allSourcesSelected}
              onSelectAll={() => void handleToggleAllSources()}
              onAddSource={() => setSourceDialogOpen(true)}
              onToggleSource={(source) => void handleToggleSource(source)}
              onDeleteSource={(sourceId) => void handleDeleteSource(sourceId)}
              mobileHidden={mobileTab !== 'sources'}
            />

            <ChatShell
              headerStatus={
                <>
                  <div className="rounded-full border border-[var(--nb-border)] bg-[var(--nb-surface)] px-3 py-2 text-[12px] leading-5 text-[var(--nb-text)]">
                    当前启用 {enabledSources.length} / {sources.length}
                  </div>
                  <button
                    type="button"
                    className="flex h-9 w-9 items-center justify-center rounded-[14px] border border-[var(--nb-border)] bg-[var(--nb-surface)] text-[var(--nb-text)] transition-colors hover:bg-[var(--nb-surface-muted)] hover:text-[var(--nb-text-strong)]"
                  >
                    <Ellipsis className="h-4 w-4" />
                  </button>
                </>
              }
              body={chatBody}
              composer={
                <ChatInput
                  enabledSources={enabledSources}
                  composer={composer}
                  onComposerChange={setComposer}
                  onKeyDown={handleComposerKeyDown}
                  onSend={() => void handleSend()}
                  sending={chatStreaming}
                />
              }
              mobileHidden={mobileTab !== 'chat'}
            />

            <section data-testid="notebook-studio-panel" hidden aria-hidden="true" className="hidden">
              <div />
            </section>

            <NotesPanel
              notes={notes}
              activeNoteId={activeNoteId}
              notesList={notesList}
              detailHeader={noteDetailHeader}
              detailBody={noteDetailBody}
              onBackToList={() => {
                setActiveNoteId(null);
                setNoteViewMode('read');
              }}
              onGenerateReport={() => void handleGenerateReport()}
              onNewNote={openNewNote}
              reportGenerating={reportGenerating}
              mobileHidden={mobileTab !== 'notes'}
            />
          </div>
        </div>
      </div>

      <Dialog open={sourceDialogOpen} onOpenChange={setSourceDialogOpen}>
        <DialogContent
          style={NOTEBOOK_THEME_STYLES}
          className="max-w-3xl overflow-hidden rounded-[var(--nb-panel-radius)] border-[var(--nb-border)] bg-[var(--nb-surface)] p-0 shadow-none"
        >
          <DialogHeader className="border-b border-[var(--nb-border)] px-6 py-5">
            <DialogTitle className="text-[20px] font-semibold text-[var(--nb-text-strong)]">Add sources</DialogTitle>
            <DialogDescription className="text-[14px] leading-6 text-[var(--nb-text)]">
              第一版支持 PDF、网页、文本和知识库文件四种来源。
            </DialogDescription>
          </DialogHeader>

          <div className="px-6 py-6">
            <div className="grid gap-3 sm:grid-cols-2">
              {SOURCE_KIND_OPTIONS.map((option) => {
                const Icon = option.icon;
                return (
                  <button
                    key={option.kind}
                    type="button"
                    className={cn(
                      'rounded-[18px] border px-4 py-4 text-left transition-colors',
                      sourceKind === option.kind
                        ? 'border-[#CDD5E3] bg-[#F8FAFC] text-[var(--nb-text-strong)]'
                        : 'border-[var(--nb-border)] bg-[var(--nb-surface)] text-[var(--nb-text-strong)] hover:bg-[var(--nb-surface-muted)]'
                    )}
                    onClick={() => setSourceKind(option.kind)}
                  >
                    <div className="flex items-start gap-3">
                      <div className="flex h-8 w-8 items-center justify-center rounded-[12px] border border-[var(--nb-border-soft)] bg-[var(--nb-surface-muted)] text-[var(--nb-text)]">
                        <Icon className="h-4 w-4" />
                      </div>
                      <div>
                        <div className="text-[15px] font-medium">{option.label}</div>
                        <div className="mt-1 text-[13px] leading-5 text-[var(--nb-text)]">{option.description}</div>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>

            <div className="mt-6 space-y-4">
              <div>
                <label className="mb-2 block text-[14px] font-medium text-[var(--nb-text-strong)]">标题</label>
                <input
                  value={sourceTitle}
                  onChange={(event) => setSourceTitle(event.target.value)}
                  placeholder="可选，自定义来源标题"
                  className="h-12 w-full rounded-[20px] border border-[var(--nb-border)] bg-[var(--nb-surface-muted)] px-4 text-[14px] text-[var(--nb-text-strong)] outline-none"
                />
              </div>
              {sourceKind === 'pdf' ? (
                <div>
                  <label className="mb-2 block text-[14px] font-medium text-[var(--nb-text-strong)]">PDF 文件</label>
                  <div className="rounded-[18px] border border-dashed border-[var(--nb-border-soft)] bg-[var(--nb-surface-muted)] p-4">
                    <input
                      ref={sourceFileInputRef}
                      type="file"
                      accept="application/pdf,.pdf"
                      onChange={(event) => setSourceFile(event.target.files?.[0] || null)}
                      data-testid="source-file-input"
                      className="sr-only"
                    />
                    <button
                      type="button"
                      className="flex w-full items-start justify-between gap-4 rounded-[16px] bg-[var(--nb-surface)] px-4 py-4 text-left transition-colors hover:bg-white"
                      onClick={() => sourceFileInputRef.current?.click()}
                      data-testid="source-file-trigger"
                    >
                      <div className="min-w-0">
                        <div className="truncate text-[15px] font-semibold text-[var(--nb-text-strong)]">
                          {sourceFile ? sourceFile.name : '选择文件'}
                        </div>
                        <div className="mt-1 text-[13px] leading-5 text-[var(--nb-text)]">
                          {sourceFile ? '已准备上传到当前 notebook' : '选择一个 PDF 文件并上传到当前 notebook'}
                        </div>
                      </div>
                      <span className="shrink-0 rounded-full border border-[var(--nb-border)] px-3 py-1.5 text-[12px] font-medium text-[var(--nb-text-strong)]">
                        浏览
                      </span>
                    </button>
                  </div>
                </div>
              ) : null}
              {sourceKind === 'url' ? (
                <div>
                  <label className="mb-2 block text-[14px] font-medium text-[var(--nb-text-strong)]">网页 URL</label>
                  <input
                    value={sourceUrl}
                    onChange={(event) => setSourceUrl(event.target.value)}
                    placeholder="https://example.com/article"
                    className="h-12 w-full rounded-[20px] border border-[var(--nb-border)] bg-[var(--nb-surface-muted)] px-4 text-[14px] text-[var(--nb-text-strong)] outline-none"
                  />
                </div>
              ) : null}
              {sourceKind === 'text' ? (
                <div>
                  <label className="mb-2 block text-[14px] font-medium text-[var(--nb-text-strong)]">文本内容</label>
                  <textarea
                    value={sourceText}
                    onChange={(event) => setSourceText(event.target.value)}
                    placeholder="粘贴文稿、会议纪要、采访内容或章节正文"
                    className="min-h-[220px] w-full rounded-[18px] border border-[var(--nb-border)] bg-[var(--nb-surface-muted)] px-4 py-3 text-[14px] leading-6 text-[var(--nb-text-strong)] outline-none"
                  />
                </div>
              ) : null}
              {sourceKind === 'kb_ref' ? (
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <label className="mb-2 block text-[14px] font-medium text-[var(--nb-text-strong)]">知识库</label>
                    <select
                      value={sourceKbId}
                      onChange={(event) => setSourceKbId(event.target.value)}
                      className="h-12 w-full rounded-[20px] border border-[var(--nb-border)] bg-[var(--nb-surface-muted)] px-4 text-[14px] text-[var(--nb-text-strong)] outline-none"
                    >
                      <option value="">选择知识库</option>
                      {kbs.map((kb) => (
                        <option key={kb.id} value={kb.id}>
                          {kb.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="mb-2 block text-[14px] font-medium text-[var(--nb-text-strong)]">文件</label>
                    <select
                      value={sourceKbFileId}
                      onChange={(event) => setSourceKbFileId(event.target.value)}
                      className="h-12 w-full rounded-[20px] border border-[var(--nb-border)] bg-[var(--nb-surface-muted)] px-4 text-[14px] text-[var(--nb-text-strong)] outline-none"
                    >
                      <option value="">选择文件</option>
                      {(selectedKb?.files || []).map((file) => (
                        <option key={file.id} value={file.id}>
                          {file.name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              ) : null}
            </div>
          </div>

          <DialogFooter className="border-t border-[var(--nb-border)] px-6 py-5">
            <Button variant="outline" className={cn('px-4', notebookUi.headerButton)} onClick={() => setSourceDialogOpen(false)}>
              <X className="h-4 w-4" />
              取消
            </Button>
            <Button className={cn('px-4', notebookUi.primaryButton)} onClick={() => void handleCreateSource()} disabled={submittingSource}>
              {submittingSource ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
              添加来源
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {activePdf ? (
        <div className="fixed inset-y-0 right-0 z-50 flex shadow-2xl">
          <PdfViewer fileUrl={activePdf.url} initialPage={activePdf.initialPage} highlightBoxes={activePdf.highlightBoxes} onClose={() => setActivePdf(null)} />
        </div>
      ) : null}
    </>
  );
}
