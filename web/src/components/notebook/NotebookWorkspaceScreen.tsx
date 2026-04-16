'use client';

import { type CSSProperties, useCallback, useEffect, useMemo, useState } from 'react';
import dynamic from 'next/dynamic';
import {
  BookOpen,
  Bot,
  CheckCircle2,
  Copy,
  FileText,
  Globe,
  LibraryBig,
  Loader2,
  MessageSquare,
  NotebookPen,
  Plus,
  Save,
  Send,
  Sparkles,
  Trash2,
  Upload,
  Waypoints,
  X,
} from 'lucide-react';
import { toast } from 'sonner';

import MarkdownRenderer from '@/components/MarkdownRenderer';
import EvidenceCard from '@/components/common/EvidenceCard';
import { cleanEvidenceTitle, type EvidenceHighlight } from '@/components/common/evidence';

const PdfViewer = dynamic(() => import('@/components/common/PdfViewer'), { ssr: false });
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
  type NotebookMindMapNode,
  type NotebookNoteDetail,
  type NotebookNoteSummary,
  type NotebookSource,
  type NotebookStudioOutput,
  type NotebookWorkspaceData,
  NotebookApiError,
  createNote,
  createNotebookSource,
  deleteNote,
  deleteNotebookSource,
  deleteNotebookStudioOutput,
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

interface NotebookWorkspaceScreenProps {
  notebookId: string;
}

type MobileTab = 'sources' | 'chat' | 'studio';
type SourceKind = CreateNotebookSourcePayload['kind'];

const SOURCE_KIND_OPTIONS: Array<{
  kind: SourceKind;
  label: string;
  description: string;
  icon: typeof Upload;
}> = [
  { kind: 'pdf', label: '上传 PDF', description: '把论文、报告或讲义导入为可检索来源。', icon: Upload },
  { kind: 'url', label: '网页链接', description: '抓取网页正文并转成 notebook 内部来源。', icon: Globe },
  { kind: 'text', label: '粘贴文本', description: '把一段正文、采访稿或会议纪要直接放进来源池。', icon: FileText },
  { kind: 'kb_ref', label: '知识库文件', description: '从现有知识库快照一份文件到当前 notebook。', icon: LibraryBig },
];

const STUDIO_OPTIONS: Array<{
  kind: NotebookStudioOutput['kind'];
  label: string;
  description: string;
  icon: typeof Sparkles;
  testId: string;
}> = [
  { kind: 'summary', label: '总结', description: '抓核心结论和主题线索。', icon: Sparkles, testId: 'studio-generate-summary' },
  { kind: 'study_guide', label: '学习指南', description: '整理重点、复习问题和学习路径。', icon: NotebookPen, testId: 'studio-generate-study_guide' },
  { kind: 'faq', label: 'FAQ', description: '把来源改写成一组常见问题与回答。', icon: MessageSquare, testId: 'studio-generate-faq' },
  { kind: 'mind_map', label: '思维导图', description: '输出概念节点和结构树。', icon: Waypoints, testId: 'studio-generate-mind_map' },
];

const NOTEBOOK_THEME_STYLES: CSSProperties & Record<string, string> = {
  '--nb-page-bg': '#F6F7FB',
  '--nb-surface': '#FFFFFF',
  '--nb-surface-muted': '#FAFBFD',
  '--nb-border': '#E6E8EF',
  '--nb-border-soft': '#ECEEF3',
  '--nb-text-strong': '#1F2430',
  '--nb-text': '#5F6B7A',
  '--nb-text-soft': '#8B95A7',
  '--nb-primary': '#111111',
  '--nb-panel-radius': '24px',
  '--nb-card-radius': '16px',
  '--nb-input-radius': '20px',
  '--nb-button-radius': '14px',
};

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

function SourceKindBadge({ kind }: { kind: NotebookSource['kind'] }) {
  const labelMap: Record<NotebookSource['kind'], string> = {
    pdf: 'PDF',
    url: '网页',
    text: '文本',
    kb_ref: '知识库',
  };
  return (
    <span className="rounded-full border border-[var(--nb-border-soft)] bg-[var(--nb-surface)] px-2 py-0.5 text-[11px] font-medium text-[var(--nb-text)]">
      {labelMap[kind]}
    </span>
  );
}

function MindMapTree({ node }: { node: NotebookMindMapNode | null }) {
  if (!node) {
    return (
      <div className="rounded-[var(--nb-card-radius)] border border-dashed border-[var(--nb-border-soft)] bg-[var(--nb-surface-muted)] p-5 text-[13px] leading-5 text-[var(--nb-text)]">
        还没有生成思维导图节点。
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <div className="inline-flex rounded-full border border-[var(--nb-border-soft)] bg-[#F4F6FA] px-4 py-2 text-[13px] font-medium text-[var(--nb-text-strong)]">
        {node.label}
      </div>
      {(node.children || []).length > 0 ? (
        <div className="grid gap-3 sm:grid-cols-2">
          {(node.children || []).map((child) => (
            <div
              key={child.id}
              className="rounded-[var(--nb-card-radius)] border border-[var(--nb-border)] bg-[var(--nb-surface)] p-4"
            >
              <div className="text-[15px] font-medium text-[var(--nb-text-strong)]">{child.label}</div>
              {(child.children || []).length > 0 ? (
                <ul className="mt-3 space-y-2 text-[13px] leading-5 text-[var(--nb-text)]">
                  {(child.children || []).map((leaf) => (
                    <li
                      key={leaf.id}
                      className="rounded-[14px] border border-[var(--nb-border-soft)] bg-[var(--nb-surface-muted)] px-3 py-2"
                    >
                      {leaf.label}
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="mt-3 text-[13px] text-[var(--nb-text-soft)]">暂无下级节点</div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded-[var(--nb-card-radius)] border border-dashed border-[var(--nb-border-soft)] bg-[var(--nb-surface-muted)] p-5 text-[13px] leading-5 text-[var(--nb-text)]">
          暂无分支节点
        </div>
      )}
    </div>
  );
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
  const [notes, setNotes] = useState<NotebookNoteSummary[]>([]);
  const [activeNoteId, setActiveNoteId] = useState<string | null>(null);
  const [activeNote, setActiveNote] = useState<NotebookNoteDetail | null>(null);
  const [mobileTab, setMobileTab] = useState<MobileTab>('chat');
  const [composer, setComposer] = useState('');
  const [chatStreaming, setChatStreaming] = useState(false);
  const [loadingWorkspace, setLoadingWorkspace] = useState(true);
  const [loadingSession, setLoadingSession] = useState(false);
  const [loadingNote, setLoadingNote] = useState(false);
  const [notesOpen, setNotesOpen] = useState(false);
  const [sourceDialogOpen, setSourceDialogOpen] = useState(false);
  const [sourceKind, setSourceKind] = useState<SourceKind>('pdf');
  const [sourceTitle, setSourceTitle] = useState('');
  const [sourceUrl, setSourceUrl] = useState('');
  const [sourceText, setSourceText] = useState('');
  const [sourceFile, setSourceFile] = useState<File | null>(null);
  const [sourceKbId, setSourceKbId] = useState('');
  const [sourceKbFileId, setSourceKbFileId] = useState('');
  const [submittingSource, setSubmittingSource] = useState(false);
  const [studioBusyKind, setStudioBusyKind] = useState<NotebookStudioOutput['kind'] | null>(null);
  const [noteSaving, setNoteSaving] = useState(false);
  const [noteDeleting, setNoteDeleting] = useState(false);
  const [noteEditor, setNoteEditor] = useState({ title: '', content: '', tags: '' });
  const [activePdf, setActivePdf] = useState<{
    url: string;
    name: string;
    initialPage: number;
    highlightBoxes?: EvidenceHighlight[];
  } | null>(null);

  const activeOutput = useMemo(
    () => studioOutputs.find((output) => output.id === activeOutputId) || studioOutputs[0] || null,
    [activeOutputId, studioOutputs]
  );

  const selectedKb = useMemo(() => kbs.find((kb) => kb.id === sourceKbId) || null, [kbs, sourceKbId]);

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
        setNotes(data.notes_summary);
        setRecentNotebookId(notebookId);

        const nextOutputId =
          options?.preferredOutputId && data.studio_outputs.some((output) => output.id === options.preferredOutputId)
            ? options.preferredOutputId
            : data.ui_defaults.active_output_id || data.studio_outputs[0]?.id || null;
        setActiveOutputId(nextOutputId);

        const nextNoteId =
          options?.preferredNoteId && data.notes_summary.some((note) => note.id === options.preferredNoteId)
            ? options.preferredNoteId
            : data.notes_summary[0]?.id || null;
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
    if (!sourceKbId && kbs.length > 0) {
      setSourceKbId(kbs[0].id);
    }
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
    if (!notesOpen || !activeNoteId) return;
    if (activeNoteId === '__draft__') {
      const draft = buildDraftNote(notebookId);
      setActiveNote(draft);
      setNoteEditor({ title: '', content: '', tags: '' });
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
      })
      .catch((error) => {
        if (!cancelled) {
          toast.error(error instanceof Error ? error.message : '加载笔记失败');
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingNote(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [activeNoteId, notebookId, notesOpen]);

  const enabledSources = useMemo(
    () => sources.filter((source) => selectedSourceIds.includes(source.id)),
    [selectedSourceIds, sources]
  );

  const handleOpenCitation = useCallback(
    (source: Parameters<typeof EvidenceCard>[0]['source']) => {
      if (!source.file_id) return;
      const kbId = workspace?.notebook.default_kb_id;
      const fileUrl = kbId
        ? `/api/kbs/${kbId}/files/${source.file_id}/content`
        : `/api/files/${source.file_id}/content`;
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
      const highlightBoxes =
        (source.highlight_boxes || []).length > 0 ? source.highlight_boxes : fallbackHighlight;
      const initialPage = parsePageNumber(
        highlightBoxes?.[0]?.page ?? source.page
      );
      setActivePdf({
        url: fileUrl,
        name: source.title || cleanEvidenceTitle(source.source),
        initialPage,
        highlightBoxes,
      });
    },
    [workspace]
  );

  const panelClass =
    'overflow-hidden rounded-[var(--nb-panel-radius)] border border-[var(--nb-border)] bg-[var(--nb-surface)]';
  const panelHeaderClass =
    'flex h-14 items-center justify-between gap-3 border-b border-[var(--nb-border)] px-4 py-3';
  const outlineButtonClass =
    'h-10 rounded-[var(--nb-button-radius)] border-[var(--nb-border)] bg-[var(--nb-surface)] text-[14px] font-medium text-[var(--nb-text-strong)] shadow-none hover:bg-[#F8FAFC] hover:text-[var(--nb-text-strong)]';
  const primaryButtonClass =
    'h-10 rounded-[var(--nb-button-radius)] bg-[var(--nb-primary)] px-4 text-[14px] font-medium text-white shadow-none hover:bg-[#1D1D1D]';

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
      if (!sourceFile) {
        toast.error('请先选择一个 PDF 文件');
        return;
      }
      payload = { kind: 'pdf', title: sourceTitle || undefined, file: sourceFile };
    } else if (sourceKind === 'url') {
      if (!sourceUrl.trim()) {
        toast.error('请填写网页 URL');
        return;
      }
      payload = { kind: 'url', title: sourceTitle || undefined, url: sourceUrl.trim() };
    } else if (sourceKind === 'text') {
      if (!sourceText.trim()) {
        toast.error('请粘贴要导入的文本内容');
        return;
      }
      payload = { kind: 'text', title: sourceTitle || undefined, text: sourceText.trim() };
    } else if (sourceKind === 'kb_ref') {
      if (!sourceKbId || !sourceKbFileId) {
        toast.error('请选择知识库和文件');
        return;
      }
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
        ? {
            ...prev,
            messages: [...prev.messages, userMessage, placeholderAssistant],
            updated_at: now,
          }
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
              if (last?.role === 'assistant') {
                messages[messages.length - 1] = { ...last, content: `${last.content || ''}${chunk}` };
              }
              return { ...prev, messages };
            });
          },
          onCitations: (citations) => {
            setActiveSession((prev) => {
              if (!prev) return prev;
              const messages = [...prev.messages];
              const last = messages[messages.length - 1];
              if (last?.role === 'assistant') {
                messages[messages.length - 1] = { ...last, citations };
              }
              return { ...prev, messages };
            });
          },
          onBackgroundExtension: (content) => {
            setActiveSession((prev) => {
              if (!prev) return prev;
              const messages = [...prev.messages];
              const last = messages[messages.length - 1];
              if (last?.role === 'assistant') {
                messages[messages.length - 1] = { ...last, background_extension: content };
              }
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
      if (error instanceof NotebookApiError) {
        toast.error(error.message);
      } else {
        toast.error(error instanceof Error ? error.message : '发送消息失败');
      }
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

  const handleGenerateStudio = useCallback(
    async (kind: NotebookStudioOutput['kind']) => {
      setStudioBusyKind(kind);
      try {
        const output = await generateNotebookStudioOutput(notebookId, {
          kind,
          source_ids: selectedSourceIds,
          session_id: activeSessionId,
        });
        setStudioOutputs((prev) => [output, ...prev.filter((item) => item.id !== output.id)]);
        setActiveOutputId(output.id);
        toast.success(`${STUDIO_OPTIONS.find((item) => item.kind === kind)?.label || 'Studio'} 已生成`);
        await loadWorkspace({
          preferredSessionId: activeSessionId,
          preferredOutputId: output.id,
          preferredNoteId: activeNoteId,
        });
      } catch (error) {
        toast.error(error instanceof Error ? error.message : '生成 Studio 产物失败');
      } finally {
        setStudioBusyKind(null);
      }
    },
    [activeNoteId, activeSessionId, loadWorkspace, notebookId, selectedSourceIds]
  );

  const handleCopyStudio = useCallback(async () => {
    if (!activeOutput) return;
    try {
      await navigator.clipboard.writeText(activeOutput.content);
      toast.success('Studio 内容已复制');
    } catch {
      toast.error('复制失败');
    }
  }, [activeOutput]);

  const handleSaveStudioAsNote = useCallback(async () => {
    if (!activeOutput) return;
    try {
      const note = await saveStudioOutputAsNote(notebookId, activeOutput.id);
      toast.success('Studio 输出已保存为笔记');
      setNotesOpen(true);
      setActiveNoteId(note.id);
      await loadWorkspace({
        preferredSessionId: activeSessionId,
        preferredOutputId: activeOutput.id,
        preferredNoteId: note.id,
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '保存 Studio 输出失败');
    }
  }, [activeOutput, activeSessionId, loadWorkspace, notebookId]);

  const handleDeleteStudio = useCallback(async () => {
    if (!activeOutput) return;
    try {
      await deleteNotebookStudioOutput(notebookId, activeOutput.id);
      const nextOutputs = studioOutputs.filter((output) => output.id !== activeOutput.id);
      setStudioOutputs(nextOutputs);
      setActiveOutputId(nextOutputs[0]?.id || null);
      toast.success('Studio 输出已删除');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '删除 Studio 输出失败');
    }
  }, [activeOutput, notebookId, studioOutputs]);

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
        setNotesOpen(true);
        setActiveNoteId(note.id);
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
    setNotesOpen(true);
    setActiveNoteId('__draft__');
    setActiveNote(buildDraftNote(notebookId));
    setNoteEditor({ title: '', content: '', tags: '' });
  }, [notebookId]);

  const handleSaveNote = useCallback(async () => {
    if (!activeNote) return;
    const title = noteEditor.title.trim();
    if (!title) {
      toast.error('请先填写笔记标题');
      return;
    }
    setNoteSaving(true);
    try {
      const payload = {
        title,
        content: noteEditor.content,
        tags: parseTags(noteEditor.tags),
      };
      const saved =
        activeNote.id === '__draft__'
          ? await createNote(notebookId, {
              ...payload,
              kind: 'manual',
              source: { type: 'manual' },
            })
          : await updateNote(notebookId, activeNote.id, payload);
      setActiveNote(saved);
      setActiveNoteId(saved.id);
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

  if (loadingWorkspace && !workspace) {
    return (
      <div
        className="flex h-full min-h-screen items-center justify-center bg-[var(--nb-page-bg)]"
        style={NOTEBOOK_THEME_STYLES}
      >
        <div className="flex items-center gap-3 rounded-full border border-[var(--nb-border)] bg-[var(--nb-surface)] px-4 py-2.5 text-[13px] text-[var(--nb-text)]">
          <Loader2 className="h-4 w-4 animate-spin" />
          正在准备智能笔记本工作台
        </div>
      </div>
    );
  }

  if (!workspace) {
    return (
      <div
        className="flex h-full min-h-screen items-center justify-center bg-[var(--nb-page-bg)]"
        style={NOTEBOOK_THEME_STYLES}
      >
        <div className="rounded-[var(--nb-panel-radius)] border border-[var(--nb-border)] bg-[var(--nb-surface)] px-8 py-9 text-center">
          <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-[16px] border border-[var(--nb-border-soft)] bg-[var(--nb-surface-muted)] text-[var(--nb-text-strong)]">
            <BookOpen className="h-6 w-6" />
          </div>
          <div className="mt-4 text-[19px] font-medium text-[var(--nb-text-strong)]">Notebook 不存在</div>
          <p className="mt-2 text-[14px] leading-6 text-[var(--nb-text)]">
            你可以返回入口页重新创建一个新的智能笔记本。
          </p>
        </div>
      </div>
    );
  }

  return (
    <>
      <div data-testid="notebook-page-root" style={NOTEBOOK_THEME_STYLES} className="min-h-screen bg-[var(--nb-page-bg)] px-4 py-4 sm:px-5 sm:py-5">
        <div className="mx-auto flex min-h-[calc(100vh-2rem)] max-w-[1820px] flex-col gap-4 lg:h-[calc(100vh-2.5rem)] lg:min-h-0">
          <header className="rounded-[var(--nb-panel-radius)] border border-[var(--nb-border)] bg-[var(--nb-surface)]">
            <div className="flex min-h-16 flex-wrap items-center justify-between gap-4 px-5 py-3 sm:px-6">
              <div className="flex min-w-0 items-center gap-3">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[16px] border border-[var(--nb-border-soft)] bg-[var(--nb-surface-muted)] text-[var(--nb-text-strong)]">
                  <BookOpen className="h-[18px] w-[18px]" />
                </div>
                <div className="min-w-0">
                  <h1 className="truncate text-[24px] leading-[28px] font-semibold text-[var(--nb-text-strong)]">
                    {workspace.notebook.name}
                  </h1>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-3">
                <div className="hidden items-center gap-2 rounded-full border border-[var(--nb-border)] bg-[var(--nb-surface)] px-3.5 py-1.5 text-[12px] leading-4 text-[var(--nb-text)] sm:flex">
                  <span>{sources.length} 个来源</span>
                  <span className="text-[var(--nb-text-soft)]">/</span>
                  <span>{notes.length} 条笔记</span>
                  <span className="text-[var(--nb-text-soft)]">/</span>
                  <span>{studioOutputs.length} 个 Studio 输出</span>
                </div>
                <Button
                  variant="outline"
                  className={cn(outlineButtonClass, 'h-9 px-4 text-[13px]')}
                  onClick={() => setSourceDialogOpen(true)}
                  data-testid="notebook-add-source"
                >
                  <Plus className="h-4 w-4" />
                  Add sources
                </Button>
                <Button
                  className={cn(primaryButtonClass, 'h-9 px-4 text-[13px]')}
                  onClick={() => setNotesOpen(true)}
                  data-testid="notebook-open-notes"
                >
                  <NotebookPen className="h-4 w-4" />
                  Add note
                </Button>
              </div>
            </div>
          </header>

          <div className="lg:hidden">
            <div className="grid grid-cols-3 gap-1.5 rounded-[20px] border border-[var(--nb-border)] bg-[var(--nb-surface)] p-1.5">
              {[
                { key: 'sources' as const, label: 'Sources' },
                { key: 'chat' as const, label: 'Chat' },
                { key: 'studio' as const, label: 'Studio' },
              ].map((tab) => (
                <button
                  key={tab.key}
                  type="button"
                  className={cn(
                    'h-10 rounded-[14px] px-3 text-[13px] font-medium text-[var(--nb-text)] transition-colors',
                    mobileTab === tab.key && 'bg-[#F4F6FA] text-[var(--nb-text-strong)]'
                  )}
                  onClick={() => setMobileTab(tab.key)}
                  data-testid={`mobile-tab-${tab.key}`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>

          <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[280px_minmax(0,1fr)_300px]">
            <section
              data-testid="notebook-sources-panel"
              className={cn(panelClass, 'min-h-[32rem] lg:min-h-0', mobileTab !== 'sources' && 'hidden lg:block')}
            >
              <div className="flex h-full flex-col">
                <div className={panelHeaderClass}>
                  <div>
                    <div className="text-base font-medium text-[var(--nb-text-strong)]">Sources</div>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-8 w-8 rounded-[12px] border-[var(--nb-border)] bg-[var(--nb-surface)] p-0 text-[var(--nb-text)] shadow-none hover:bg-[#F8FAFC]"
                    onClick={() => setSourceDialogOpen(true)}
                  >
                    <Plus className="h-4 w-4" />
                  </Button>
                </div>

                <ScrollArea className="min-h-0 flex-1 px-4 py-4">
                  <div className="space-y-3">
                    {sources.length === 0 ? (
                      <div className="rounded-[var(--nb-card-radius)] border border-dashed border-[var(--nb-border-soft)] bg-[var(--nb-surface-muted)] px-4 py-6 text-center">
                        <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-[14px] border border-[var(--nb-border-soft)] bg-[var(--nb-surface)] text-[var(--nb-text-strong)]">
                          <BookOpen className="h-[18px] w-[18px]" />
                        </div>
                        <div className="mt-3 text-[18px] font-medium text-[var(--nb-text-strong)]">还没有来源</div>
                        <p className="mx-auto mt-2 max-w-[15rem] text-[13px] leading-5 text-[var(--nb-text)]">
                          先加入 PDF、网页、文本或知识库文件，聊天和 Studio 才会更可靠。
                        </p>
                        <Button className={cn(primaryButtonClass, 'mt-4 h-9 px-4 text-[13px]')} onClick={() => setSourceDialogOpen(true)}>
                          <Plus className="h-4 w-4" />
                          添加第一个来源
                        </Button>
                      </div>
                    ) : (
                      sources.map((source) => (
                        <div
                          key={source.id}
                          className={cn(
                            'rounded-[var(--nb-card-radius)] border px-3.5 py-3.5 transition-colors',
                            source.included
                              ? 'border-[#CDD5E3] bg-[#F8FAFC]'
                              : 'border-[var(--nb-border)] bg-[var(--nb-surface)] hover:bg-[var(--nb-surface-muted)]'
                          )}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <div className="flex flex-wrap items-center gap-2">
                                <SourceKindBadge kind={source.kind} />
                                {source.included ? (
                                  <span className="inline-flex items-center gap-1 rounded-full bg-[#EEF3FA] px-2 py-0.5 text-[11px] font-medium text-[var(--nb-text)]">
                                    <CheckCircle2 className="h-3.5 w-3.5" />
                                    已启用
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center gap-1 rounded-full bg-[#F7F8FB] px-2 py-0.5 text-[11px] font-medium text-[var(--nb-text-soft)]">
                                    未启用
                                  </span>
                                )}
                              </div>
                              <div className="mt-2.5 line-clamp-2 text-[14px] font-medium leading-5 text-[var(--nb-text-strong)]">
                                {source.title}
                              </div>
                              <p className="mt-1.5 line-clamp-3 text-[12px] leading-5 text-[var(--nb-text)]">{source.snippet}</p>
                              <div className="mt-3 flex flex-wrap items-center gap-2 text-[12px] leading-5 text-[var(--nb-text-soft)]">
                                <span>{source.chunk_count} chunks</span>
                                <span>{source.word_count} words</span>
                                <span>{formatDateTime(source.updated_at)}</span>
                              </div>
                            </div>
                            <div className="flex shrink-0 flex-col gap-2">
                              <Button
                                size="sm"
                                variant="outline"
                                className="h-8 rounded-[12px] border-[var(--nb-border)] bg-[var(--nb-surface)] px-3 text-[12px] font-medium text-[var(--nb-text-strong)] shadow-none hover:bg-[#F8FAFC]"
                                onClick={() => void handleToggleSource(source)}
                              >
                                {source.included ? '停用' : '启用'}
                              </Button>
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-8 w-8 rounded-[12px] p-0 text-[var(--nb-text-soft)] hover:bg-[#F4F6FA] hover:text-[var(--nb-text-strong)]"
                                onClick={() => void handleDeleteSource(source.id)}
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </div>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </ScrollArea>
              </div>
            </section>

            <section
              data-testid="notebook-chat-panel"
              className={cn(panelClass, 'min-h-[32rem] lg:min-h-0', mobileTab !== 'chat' && 'hidden lg:block')}
            >
              <div className="flex h-full flex-col">
                <div className={panelHeaderClass}>
                  <div>
                    <div className="text-base font-medium text-[var(--nb-text-strong)]">Chat</div>
                  </div>
                  <div className="rounded-full border border-[var(--nb-border)] bg-[var(--nb-surface)] px-3 py-2 text-[12px] leading-5 text-[var(--nb-text)]">
                    当前启用 {enabledSources.length} / {sources.length}
                  </div>
                </div>

                {sessions.length > 0 ? (
                  <div className="border-b border-[var(--nb-border)] px-4 py-3">
                    <div className="flex gap-2 overflow-x-auto pb-1">
                      {sessions.map((session) => (
                        <button
                          key={session.id}
                          type="button"
                          className={cn(
                            'min-w-[176px] rounded-[var(--nb-card-radius)] border px-4 py-3 text-left transition-colors',
                            activeSessionId === session.id
                              ? 'border-[#CDD5E3] bg-[#F8FAFC] text-[var(--nb-text-strong)]'
                              : 'border-[var(--nb-border)] bg-[var(--nb-surface)] text-[var(--nb-text)] hover:bg-[var(--nb-surface-muted)]'
                          )}
                          onClick={() => void loadSession(session.id)}
                        >
                          <div className="truncate text-[14px] font-medium">{session.title}</div>
                          <div className="mt-1 line-clamp-2 text-[12px] leading-5 text-[var(--nb-text-soft)]">
                            {session.last_message || `${session.message_count} 条消息`}
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}

                <ScrollArea className="min-h-0 flex-1 px-4 py-4">
                  {loadingSession ? (
                    <div className="flex h-full items-center justify-center text-[13px] text-[var(--nb-text)]">
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      正在加载对话
                    </div>
                  ) : activeSession?.messages.length ? (
                    <div className="space-y-3">
                      {activeSession.messages.map((message) => {
                        const isAssistant = message.role === 'assistant';
                        return (
                          <div
                            key={message.id}
                            className={cn(
                              'rounded-[var(--nb-card-radius)] border p-4',
                              isAssistant
                                ? 'border-[var(--nb-border)] bg-[var(--nb-surface)]'
                                : 'ml-auto max-w-[88%] border-[#E0E6EF] bg-[#F5F7FB]'
                            )}
                          >
                            <div className="mb-3 flex items-center justify-between gap-3">
                              <div className="flex items-center gap-2 text-[13px] font-medium text-[var(--nb-text-strong)]">
                                <div className="flex h-8 w-8 items-center justify-center rounded-[12px] border border-[var(--nb-border-soft)] bg-[var(--nb-surface-muted)] text-[var(--nb-text-strong)]">
                                  {isAssistant ? <Bot className="h-4 w-4" /> : <MessageSquare className="h-4 w-4" />}
                                </div>
                                <span>{isAssistant ? 'Notebook Assistant' : 'You'}</span>
                              </div>
                              <div className="text-[12px] text-[var(--nb-text-soft)]">{formatDateTime(message.created_at)}</div>
                            </div>

                            {isAssistant ? (
                              <MarkdownRenderer
                                className="prose-p:text-[14px] prose-p:leading-6 prose-li:text-[14px] prose-li:leading-6 prose-headings:text-[15px] prose-headings:leading-6 prose-strong:text-[var(--nb-text-strong)] prose-p:text-[var(--nb-text)] prose-li:text-[var(--nb-text)]"
                                content={message.content || (chatStreaming ? '正在组织答案…' : '')}
                                sources={citationSources(message.citations || [])}
                              />
                            ) : (
                              <div className="whitespace-pre-wrap text-[14px] leading-6 text-[var(--nb-text-strong)]">
                                {message.content}
                              </div>
                            )}

                            {isAssistant && message.background_extension ? (
                              <div className="mt-4 rounded-[var(--nb-card-radius)] border border-[#F1E0B2] bg-[#FFF8E7] px-4 py-3 text-[13px] leading-6 text-[#8A6520]">
                                <div className="mb-1 font-medium">背景补充</div>
                                <div className="whitespace-pre-wrap">{message.background_extension}</div>
                              </div>
                            ) : null}

                            {isAssistant && (message.citations || []).length > 0 ? (
                              <div className="mt-4 rounded-[var(--nb-card-radius)] border border-[var(--nb-border-soft)] bg-[var(--nb-surface-muted)] px-4 py-3">
                                <div className="mb-2 text-[11px] font-medium uppercase tracking-[0.22em] text-[var(--nb-text-soft)]">
                                  Citations
                                </div>
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
                                      onOpen={citation.source_id ? handleOpenCitation : undefined}
                                    />
                                  ))}
                                </div>
                              </div>
                            ) : null}

                            {isAssistant ? (
                              <div className="mt-4 flex flex-wrap gap-2">
                                <Button
                                  size="sm"
                                  variant="outline"
                                  className="h-9 rounded-[12px] border-[var(--nb-border)] bg-[var(--nb-surface)] px-3 text-[13px] font-medium text-[var(--nb-text-strong)] shadow-none hover:bg-[#F8FAFC]"
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
                    <div className="flex h-full flex-col items-center justify-center px-6 py-8 text-center">
                      <div className="flex h-12 w-12 items-center justify-center rounded-[16px] border border-[var(--nb-border-soft)] bg-[var(--nb-surface-muted)] text-[var(--nb-text-strong)]">
                        <Bot className="h-5 w-5" />
                      </div>
                      <h2 className="mt-3 text-[24px] leading-[28px] font-semibold tracking-tight text-[var(--nb-text-strong)]">
                        {workspace.notebook.name}
                      </h2>
                      <div className="mt-4 flex flex-wrap justify-center gap-2">
                        {['帮我快速总结这些来源', '提炼这批资料的关键概念', '把它整理成可复习的问题集'].map((prompt) => (
                          <button
                            key={prompt}
                            type="button"
                            className="h-9 rounded-full border border-[var(--nb-border-soft)] bg-[var(--nb-surface)] px-4 text-[13px] font-medium text-[var(--nb-text)] transition-colors hover:bg-[var(--nb-surface-muted)] hover:text-[var(--nb-text-strong)]"
                            onClick={() => setComposer(prompt)}
                          >
                            {prompt}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </ScrollArea>

                <div className="border-t border-[var(--nb-border)] px-4 py-4">
                  <div className="mb-3 flex flex-wrap items-center gap-2 text-[12px] leading-5 text-[var(--nb-text-soft)]">
                    <span>本次回答将使用：</span>
                    {enabledSources.length > 0 ? (
                      enabledSources.map((source) => (
                        <span
                          key={source.id}
                          className="rounded-full border border-[var(--nb-border-soft)] bg-[var(--nb-surface-muted)] px-2.5 py-1 text-[12px] text-[var(--nb-text)]"
                        >
                          {source.title}
                        </span>
                      ))
                    ) : (
                      <span className="rounded-full bg-[#FFF4E6] px-2.5 py-1 text-[12px] text-[#B56A20]">
                        当前没有启用来源，建议先打开至少一个来源
                      </span>
                    )}
                  </div>
                  <div className="flex items-end gap-3 rounded-[var(--nb-input-radius)] border border-[var(--nb-border)] bg-[var(--nb-surface)] px-4 py-3">
                    <textarea
                      value={composer}
                      onChange={(event) => setComposer(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' && !event.shiftKey) {
                          event.preventDefault();
                          void handleSend();
                        }
                      }}
                      placeholder="Start typing..."
                      className="min-h-[56px] max-h-40 flex-1 resize-none bg-transparent py-1 text-[14px] leading-6 text-[var(--nb-text-strong)] outline-none placeholder:text-[var(--nb-text-soft)]"
                      data-testid="notebook-chat-input"
                    />
                    <Button
                      className="h-10 w-10 rounded-[14px] bg-[var(--nb-primary)] p-0 text-white shadow-none hover:bg-[#1D1D1D]"
                      onClick={() => void handleSend()}
                      disabled={chatStreaming || !composer.trim()}
                      data-testid="notebook-chat-send"
                    >
                      {chatStreaming ? <Loader2 className="h-[18px] w-[18px] animate-spin" /> : <Send className="h-[18px] w-[18px]" />}
                    </Button>
                  </div>
                </div>
              </div>
            </section>

            <section
              data-testid="notebook-studio-panel"
              className={cn(panelClass, 'min-h-[32rem] lg:min-h-0 lg:h-full', mobileTab !== 'studio' && 'hidden lg:block')}
            >
              <div className="flex h-full min-h-0 flex-col">
                <div className={cn(panelHeaderClass, 'shrink-0')}>
                  <div>
                    <div className="text-base font-medium text-[var(--nb-text-strong)]">Studio</div>
                  </div>
                </div>

                <div className="shrink-0 border-b border-[var(--nb-border)] px-3 py-3 lg:h-[168px]">
                  <div className="grid gap-2.5 sm:grid-cols-2 lg:h-full lg:auto-rows-fr">
                    {STUDIO_OPTIONS.map((option) => {
                      const Icon = option.icon;
                      const busy = studioBusyKind === option.kind;
                      return (
                        <button
                          key={option.kind}
                          type="button"
                          className="rounded-[14px] border border-[var(--nb-border)] bg-[var(--nb-surface)] px-3.5 py-2.5 text-left transition-colors hover:bg-[var(--nb-surface-muted)] lg:h-full"
                          onClick={() => void handleGenerateStudio(option.kind)}
                          disabled={busy}
                          data-testid={option.testId}
                        >
                          <div className="flex items-center gap-3">
                            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[10px] border border-[var(--nb-border-soft)] bg-[var(--nb-surface-muted)] text-[var(--nb-text-strong)]">
                              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Icon className="h-4 w-4" />}
                            </div>
                            <div className="min-w-0 flex-1">
                              <div className="text-[14px] font-medium text-[var(--nb-text-strong)]">{option.label}</div>
                            </div>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="min-h-0 flex-1">
                  <ScrollArea className="h-full min-h-0 px-4 py-4">
                    {activeOutput ? (
                      <div className="space-y-4">
                        <div className="rounded-[var(--nb-card-radius)] border border-[var(--nb-border)] bg-[var(--nb-surface)] p-4">
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div>
                              <div className="text-[11px] uppercase tracking-[0.24em] text-[var(--nb-text-soft)]">
                                {activeOutput.kind.replace('_', ' ')}
                              </div>
                              <h3 className="mt-2 text-[20px] leading-7 font-semibold text-[var(--nb-text-strong)]">
                                {activeOutput.title}
                              </h3>
                              <div className="mt-2 text-[12px] leading-5 text-[var(--nb-text-soft)]">
                                {activeOutput.source_ids.length} 个来源 · {formatDateTime(activeOutput.updated_at)}
                              </div>
                            </div>
                            <div className="flex flex-wrap gap-2">
                              <Button
                                size="sm"
                                variant="outline"
                                className="h-9 rounded-[12px] border-[var(--nb-border)] bg-[var(--nb-surface)] px-3 text-[13px] font-medium text-[var(--nb-text-strong)] shadow-none hover:bg-[#F8FAFC]"
                                onClick={() => void handleCopyStudio()}
                              >
                                <Copy className="h-4 w-4" />
                                复制
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                className="h-9 rounded-[12px] border-[var(--nb-border)] bg-[var(--nb-surface)] px-3 text-[13px] font-medium text-[var(--nb-text-strong)] shadow-none hover:bg-[#F8FAFC]"
                                onClick={() => void handleSaveStudioAsNote()}
                              >
                                <Save className="h-4 w-4" />
                                保存为笔记
                              </Button>
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-9 w-9 rounded-[12px] p-0 text-[var(--nb-text-soft)] hover:bg-[#F4F6FA] hover:text-[var(--nb-text-strong)]"
                                onClick={() => void handleDeleteStudio()}
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </div>
                          </div>

                          <div className="mt-5">
                            {activeOutput.kind === 'mind_map' ? (
                              <MindMapTree node={activeOutput.tree} />
                            ) : (
                              <MarkdownRenderer
                                className="prose-p:text-[14px] prose-p:leading-6 prose-li:text-[14px] prose-li:leading-6 prose-headings:text-[15px] prose-headings:leading-6 prose-p:text-[var(--nb-text)] prose-li:text-[var(--nb-text)] prose-strong:text-[var(--nb-text-strong)]"
                                content={activeOutput.content}
                                sources={citationSources(activeOutput.citations)}
                              />
                            )}
                          </div>

                          {activeOutput.blocks.length > 0 ? (
                            <div className="mt-5 grid gap-3">
                              {activeOutput.blocks.map((block, index) => (
                                <div
                                  key={`${activeOutput.id}:${index}`}
                                  className="rounded-[var(--nb-card-radius)] border border-[var(--nb-border-soft)] bg-[var(--nb-surface-muted)] px-4 py-4"
                                >
                                  <div className="text-[15px] font-medium text-[var(--nb-text-strong)]">{block.title}</div>
                                  <ul className="mt-3 space-y-2 text-[13px] leading-5 text-[var(--nb-text)]">
                                    {block.items.map((item, itemIndex) => (
                                      <li
                                        key={`${activeOutput.id}:${index}:${itemIndex}`}
                                        className="rounded-[12px] border border-[var(--nb-border-soft)] bg-[var(--nb-surface)] px-3 py-2"
                                      >
                                        {item}
                                      </li>
                                    ))}
                                  </ul>
                                </div>
                              ))}
                            </div>
                          ) : null}
                        </div>

                        {studioOutputs.length > 1 ? (
                          <div className="space-y-3">
                            <div className="text-[13px] font-medium text-[var(--nb-text-strong)]">最近生成</div>
                            {studioOutputs.map((output) => (
                              <button
                                key={output.id}
                                type="button"
                                className={cn(
                                  'w-full rounded-[var(--nb-card-radius)] border px-4 py-4 text-left transition-colors',
                                  activeOutputId === output.id
                                    ? 'border-[#CDD5E3] bg-[#F8FAFC] text-[var(--nb-text-strong)]'
                                    : 'border-[var(--nb-border)] bg-[var(--nb-surface)] text-[var(--nb-text)] hover:bg-[var(--nb-surface-muted)]'
                                )}
                                onClick={() => setActiveOutputId(output.id)}
                              >
                                <div className="flex items-center justify-between gap-3">
                                  <div>
                                    <div className="text-[15px] font-medium">{output.title}</div>
                                    <div className="mt-1 text-[12px] leading-5 text-[var(--nb-text-soft)]">
                                      {output.kind} · {formatDateTime(output.updated_at)}
                                    </div>
                                  </div>
                                  <Sparkles className="h-4 w-4 text-[var(--nb-text-soft)]" />
                                </div>
                              </button>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    ) : (
                      <div className="flex min-h-full flex-col items-center justify-center rounded-[var(--nb-card-radius)] border border-dashed border-[var(--nb-border-soft)] bg-[var(--nb-surface-muted)] px-6 text-center">
                        <div className="flex h-10 w-10 items-center justify-center rounded-[14px] border border-[var(--nb-border-soft)] bg-[var(--nb-surface)] text-[var(--nb-text-strong)]">
                          <Sparkles className="h-[18px] w-[18px]" />
                        </div>
                        <div className="mt-4 text-[19px] font-medium text-[var(--nb-text-strong)]">Studio output will be saved here</div>
                      </div>
                    )}
                  </ScrollArea>
                </div>
              </div>
            </section>
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
                      'rounded-[var(--nb-card-radius)] border px-4 py-4 text-left transition-colors',
                      sourceKind === option.kind
                        ? 'border-[#CDD5E3] bg-[#F8FAFC] text-[var(--nb-text-strong)]'
                        : 'border-[var(--nb-border)] bg-[var(--nb-surface)] text-[var(--nb-text-strong)] hover:bg-[var(--nb-surface-muted)]'
                    )}
                    onClick={() => setSourceKind(option.kind)}
                  >
                    <div className="flex items-start gap-3">
                      <div
                        className={cn(
                          'flex h-8 w-8 items-center justify-center rounded-[12px] border border-[var(--nb-border-soft)] bg-[var(--nb-surface-muted)]',
                          sourceKind === option.kind ? 'text-[var(--nb-text-strong)]' : 'text-[var(--nb-text)]'
                        )}
                      >
                        <Icon className="h-4 w-4" />
                      </div>
                      <div>
                        <div className="text-[15px] font-medium">{option.label}</div>
                        <div className="mt-1 text-[13px] leading-5 text-[var(--nb-text)]">
                          {option.description}
                        </div>
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
                  className="h-12 w-full rounded-[var(--nb-input-radius)] border border-[var(--nb-border)] bg-[var(--nb-surface-muted)] px-4 text-[14px] text-[var(--nb-text-strong)] outline-none ring-0 transition focus:border-[#CDD5E3]"
                />
              </div>

              {sourceKind === 'pdf' ? (
                <div>
                  <label className="mb-2 block text-[14px] font-medium text-[var(--nb-text-strong)]">PDF 文件</label>
                  <div className="rounded-[var(--nb-card-radius)] border border-dashed border-[var(--nb-border-soft)] bg-[var(--nb-surface-muted)] p-4">
                    <input
                      type="file"
                      accept="application/pdf,.pdf"
                      onChange={(event) => setSourceFile(event.target.files?.[0] || null)}
                      data-testid="source-file-input"
                    />
                    <div className="mt-2 text-[13px] leading-5 text-[var(--nb-text)]">
                      {sourceFile ? `已选择：${sourceFile.name}` : '选择一个 PDF 文件并上传到当前 notebook'}
                    </div>
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
                    className="h-12 w-full rounded-[var(--nb-input-radius)] border border-[var(--nb-border)] bg-[var(--nb-surface-muted)] px-4 text-[14px] text-[var(--nb-text-strong)] outline-none ring-0 transition focus:border-[#CDD5E3]"
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
                    className="min-h-[220px] w-full rounded-[var(--nb-card-radius)] border border-[var(--nb-border)] bg-[var(--nb-surface-muted)] px-4 py-3 text-[14px] leading-6 text-[var(--nb-text-strong)] outline-none ring-0 transition focus:border-[#CDD5E3]"
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
                      className="h-12 w-full rounded-[var(--nb-input-radius)] border border-[var(--nb-border)] bg-[var(--nb-surface-muted)] px-4 text-[14px] text-[var(--nb-text-strong)] outline-none"
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
                      className="h-12 w-full rounded-[var(--nb-input-radius)] border border-[var(--nb-border)] bg-[var(--nb-surface-muted)] px-4 text-[14px] text-[var(--nb-text-strong)] outline-none"
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
            <Button variant="outline" className={cn('px-4', outlineButtonClass)} onClick={() => setSourceDialogOpen(false)}>
              <X className="h-4 w-4" />
              取消
            </Button>
            <Button
              className={cn('px-4', primaryButtonClass)}
              onClick={() => void handleCreateSource()}
              disabled={submittingSource}
            >
              {submittingSource ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              添加来源
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={notesOpen} onOpenChange={setNotesOpen}>
        <DialogContent
          style={NOTEBOOK_THEME_STYLES}
          className="h-[92vh] max-w-6xl overflow-hidden rounded-[var(--nb-panel-radius)] border-[var(--nb-border)] bg-[var(--nb-surface)] p-0 shadow-none"
          data-testid="notebook-notes-drawer"
        >
          <div className="grid h-full grid-cols-1 lg:grid-cols-[300px_minmax(0,1fr)]">
            <div className="border-b border-[var(--nb-border)] lg:border-b-0 lg:border-r">
              <div className="border-b border-[var(--nb-border)] px-5 py-5">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-base font-medium text-[var(--nb-text-strong)]">Notes</div>
                    <div className="mt-1 text-[13px] leading-5 text-[var(--nb-text)]">保存聊天、Studio 结果或手动记录。</div>
                  </div>
                  <Button size="sm" className="h-9 rounded-[12px] bg-[var(--nb-primary)] px-3 text-[13px] text-white shadow-none hover:bg-[#1D1D1D]" onClick={openNewNote}>
                    <Plus className="h-4 w-4" />
                    新建
                  </Button>
                </div>
              </div>
              <ScrollArea className="h-[280px] px-4 py-4 lg:h-[calc(92vh-92px)]">
                <div className="space-y-3">
                  {notes.length === 0 ? (
                    <div className="rounded-[var(--nb-card-radius)] border border-dashed border-[var(--nb-border-soft)] bg-[var(--nb-surface-muted)] px-4 py-6 text-center text-[13px] text-[var(--nb-text)]">
                      这里还没有保存的笔记。
                    </div>
                  ) : (
                    notes.map((note) => (
                      <button
                        key={note.id}
                        type="button"
                        className={cn(
                          'w-full rounded-[var(--nb-card-radius)] border px-4 py-4 text-left transition-colors',
                          activeNoteId === note.id
                            ? 'border-[#CDD5E3] bg-[#F8FAFC] text-[var(--nb-text-strong)]'
                            : 'border-[var(--nb-border)] bg-[var(--nb-surface)] text-[var(--nb-text-strong)] hover:bg-[var(--nb-surface-muted)]'
                        )}
                        onClick={() => setActiveNoteId(note.id)}
                      >
                        <div className="text-[15px] font-medium">{note.title}</div>
                        <div className="mt-2 text-[13px] leading-5 text-[var(--nb-text)]">
                          {note.preview || '暂无摘要'}
                        </div>
                        {note.tags.length > 0 ? (
                          <div className="mt-3 flex flex-wrap gap-1.5">
                            {note.tags.map((tag) => (
                              <span
                                key={`${note.id}:${tag}`}
                                className="rounded-full border border-[var(--nb-border-soft)] bg-[var(--nb-surface)] px-2 py-0.5 text-[11px] text-[var(--nb-text-soft)]"
                              >
                                {tag}
                              </span>
                            ))}
                          </div>
                        ) : null}
                      </button>
                    ))
                  )}
                </div>
              </ScrollArea>
            </div>

            <div className="flex h-full flex-col">
              <div className="border-b border-[var(--nb-border)] px-5 py-5">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-base font-medium text-[var(--nb-text-strong)]">
                      {activeNoteId === '__draft__' ? '新建笔记' : activeNote?.title || '选择一条笔记'}
                    </div>
                    <div className="mt-1 text-[13px] leading-5 text-[var(--nb-text)]">
                      {activeNote?.kind === 'saved_chat'
                        ? '来自聊天对话'
                        : activeNote?.kind === 'saved_studio'
                          ? '来自 Studio 输出'
                          : activeNote?.kind === 'saved_research'
                            ? '来自研究工作流'
                            : '手动整理的长期笔记'}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {activeNote && activeNote.id !== '__draft__' ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-9 rounded-[12px] px-3 text-[13px] text-[var(--nb-text-soft)] hover:bg-[#F4F6FA] hover:text-[var(--nb-text-strong)]"
                        onClick={() => void handleDeleteNote()}
                        disabled={noteDeleting}
                      >
                        {noteDeleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                        删除
                      </Button>
                    ) : null}
                    <Button
                      size="sm"
                      className="h-9 rounded-[12px] bg-[var(--nb-primary)] px-3 text-[13px] text-white shadow-none hover:bg-[#1D1D1D]"
                      onClick={() => void handleSaveNote()}
                      disabled={noteSaving || (!activeNote && activeNoteId !== '__draft__')}
                    >
                      {noteSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                      保存
                    </Button>
                  </div>
                </div>
              </div>

              <ScrollArea className="flex-1 px-5 py-5">
                {loadingNote ? (
                  <div className="flex h-full items-center justify-center text-[13px] text-[var(--nb-text)]">
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    正在加载笔记
                  </div>
                ) : activeNote ? (
                  <div className="space-y-5">
                    <div className="grid gap-4">
                      <div>
                        <label className="mb-2 block text-[14px] font-medium text-[var(--nb-text-strong)]">标题</label>
                        <input
                          value={noteEditor.title}
                          onChange={(event) => setNoteEditor((prev) => ({ ...prev, title: event.target.value }))}
                          className="h-12 w-full rounded-[var(--nb-input-radius)] border border-[var(--nb-border)] bg-[var(--nb-surface-muted)] px-4 text-[14px] text-[var(--nb-text-strong)] outline-none"
                        />
                      </div>
                      <div>
                        <label className="mb-2 block text-[14px] font-medium text-[var(--nb-text-strong)]">标签</label>
                        <input
                          value={noteEditor.tags}
                          onChange={(event) => setNoteEditor((prev) => ({ ...prev, tags: event.target.value }))}
                          placeholder="用逗号分隔，例如 rag, benchmark"
                          className="h-12 w-full rounded-[var(--nb-input-radius)] border border-[var(--nb-border)] bg-[var(--nb-surface-muted)] px-4 text-[14px] text-[var(--nb-text-strong)] outline-none"
                        />
                      </div>
                      <div>
                        <label className="mb-2 block text-[14px] font-medium text-[var(--nb-text-strong)]">内容</label>
                        <textarea
                          value={noteEditor.content}
                          onChange={(event) => setNoteEditor((prev) => ({ ...prev, content: event.target.value }))}
                          className="min-h-[280px] w-full rounded-[var(--nb-card-radius)] border border-[var(--nb-border)] bg-[var(--nb-surface-muted)] px-4 py-3 text-[14px] leading-6 text-[var(--nb-text-strong)] outline-none"
                        />
                      </div>
                    </div>

                    {activeNote.citations.length > 0 ? (
                      <div className="rounded-[var(--nb-card-radius)] border border-[var(--nb-border)] bg-[var(--nb-surface-muted)] px-5 py-5">
                        <div className="mb-3 text-[15px] font-medium text-[var(--nb-text-strong)]">关联引用</div>
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
                  </div>
                ) : (
                  <div className="flex h-full items-center justify-center rounded-[var(--nb-card-radius)] border border-dashed border-[var(--nb-border-soft)] bg-[var(--nb-surface-muted)] text-[13px] text-[var(--nb-text)]">
                    选择一条笔记，或点击左上角新建。
                  </div>
                )}
              </ScrollArea>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* PDF Viewer overlay – slides in from the right */}
      {activePdf ? (
        <div className="fixed inset-y-0 right-0 z-50 flex shadow-2xl">
          <PdfViewer
            fileUrl={activePdf.url}
            initialPage={activePdf.initialPage}
            highlightBoxes={activePdf.highlightBoxes}
            onClose={() => setActivePdf(null)}
          />
        </div>
      ) : null}
    </>
  );
}
