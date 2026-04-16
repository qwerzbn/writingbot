'use client';

import type { EvidenceInterpretation } from '@/components/common/evidence';

export interface NotebookListRow {
  id: string;
  name: string;
  description: string;
  color?: string;
  icon?: string;
  source_count: number;
  note_count: number;
  last_chat_at?: string | null;
  last_output_at?: string | null;
  created_at: string;
  updated_at: string;
  default_kb_id?: string | null;
  auto_import_enabled?: boolean;
  record_count?: number;
}

export interface NotebookKbOption {
  id: string;
  name: string;
}

export interface NotebookJob {
  id: string;
  job_type: string;
  status: 'pending' | 'running' | 'done' | 'partial_failed' | 'error';
  progress: number;
  processed?: number;
  total?: number;
  kb_id?: string | null;
  trigger_mode?: string;
  note_ids?: string[];
  updated_at?: string;
  message?: string;
}

export interface NotebookCitation {
  index: number;
  source_id: string;
  source_title: string;
  locator: string;
  excerpt: string;
  page?: number | string;
  line_start?: number;
  line_end?: number;
  bbox?: number[];
  page_width?: number;
  page_height?: number;
  highlight_boxes?: Array<{
    page?: number;
    bbox?: number[];
    line_start?: number;
    line_end?: number;
    page_width?: number;
    page_height?: number;
  }>;
  summary?: string;
  title?: string;
  asset_id?: string;
  asset_type?: string;
  caption?: string;
  ref_label?: string;
  thumbnail_url?: string;
  interpretation?: EvidenceInterpretation;
  is_primary?: boolean;
  evidence_kind?: string;
}

export interface NotebookSource {
  id: string;
  notebook_id: string;
  kind: 'pdf' | 'url' | 'text' | 'kb_ref';
  title: string;
  included: boolean;
  status: string;
  snippet: string;
  word_count: number;
  char_count: number;
  chunk_count: number;
  created_at: string;
  updated_at: string;
  metadata: {
    url?: string;
    kb_id?: string;
    file_id?: string;
    file_name?: string;
    asset_path?: string;
    source?: string;
    [key: string]: unknown;
  };
}

export interface NotebookChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  background_extension?: string;
  citations?: NotebookCitation[];
  source_ids: string[];
  created_at: string;
}

export interface NotebookChatSessionSummary {
  id: string;
  title: string;
  updated_at: string;
  created_at: string;
  message_count: number;
  last_message: string;
}

export interface NotebookChatSessionDetail {
  id: string;
  notebook_id: string;
  title: string;
  messages: NotebookChatMessage[];
  created_at: string;
  updated_at: string;
}

export interface NotebookStudioBlock {
  title: string;
  items: string[];
}

export interface NotebookMindMapNode {
  id: string;
  label: string;
  children?: NotebookMindMapNode[];
}

export interface NotebookStudioOutput {
  id: string;
  notebook_id: string;
  kind: 'summary' | 'study_guide' | 'faq' | 'mind_map';
  title: string;
  content: string;
  blocks: NotebookStudioBlock[];
  tree: NotebookMindMapNode | null;
  citations: NotebookCitation[];
  source_ids: string[];
  created_at: string;
  updated_at: string;
}

export interface NotebookNoteSummary {
  id: string;
  title: string;
  kind: 'manual' | 'saved_chat' | 'saved_research' | 'saved_studio';
  preview: string;
  tags: string[];
  source_ids: string[];
  updated_at: string;
  created_at: string;
  origin?: string | null;
  citations: NotebookCitation[];
}

export interface WorkspaceNoteSummary {
  id: string;
  notebook_id: string;
  title: string;
  tags: string[];
  source: {
    type?: string;
    file_name?: string;
    kb_id?: string;
    file_id?: string;
    page?: number;
    citation_count?: number;
    evidence_links?: Array<{ id?: string; source?: string; page?: number | string; content?: string }>;
  };
  kb_id?: string;
  file_id?: string;
  concepts?: string[];
  links_count?: number;
  mastery_score?: number;
  template_completeness?: number;
  content_preview?: string;
  ai_summary?: string;
  has_ai_summary?: boolean;
  ai_summary_updated_at?: string;
  source_label?: string;
  created_at: string;
  updated_at: string;
}

export interface NotebookNoteDetail {
  id: string;
  notebook_id: string;
  title: string;
  content: string;
  kind: 'manual' | 'saved_chat' | 'saved_research' | 'saved_studio';
  origin?: string | null;
  citations: NotebookCitation[];
  source_ids: string[];
  tags: string[];
  created_at: string;
  updated_at: string;
  source: {
    type?: string;
    kb_id?: string;
    file_id?: string;
    file_name?: string;
    page?: number;
    chunk_id?: string;
    original_quote?: string;
    evidence_links?: Array<{ id?: string; source?: string; page?: number | string; content?: string }>;
    citation_count?: number;
    last_used_at?: string;
  };
  ai_meta?: {
    summary?: string;
    suggested_tags?: string[];
  };
}

export interface NotebookNoteMeta {
  summary?: string;
  suggested_tags?: string[];
  related_notes?: Array<{ id: string; title: string; score?: number; notebook_name?: string }>;
  paper_card?: Record<string, unknown>;
  source_spans?: Array<{ id?: string; source?: string; page?: number | string; content?: string }>;
  extraction_status?: string;
  updated_at?: string;
}

export interface GraphViewPayload {
  notebook_id: string;
  updated_at?: string;
  metrics?: {
    note_count?: number;
    concept_count?: number;
    edge_count?: number;
    note_relation_count?: number;
  };
  nodes: Array<{
    id: string;
    kind: 'note' | 'concept';
    label: string;
    subtitle: string;
    mastery_score?: number | null;
    note_id?: string;
  }>;
  edges: Array<{
    id: string;
    kind: string;
    source_id?: string;
    target_id?: string;
    source_label: string;
    target_label: string;
    relation_label: string;
    score: number;
  }>;
}

export interface RelatedNote {
  id: string;
  notebook_id?: string;
  notebook_name?: string;
  title: string;
  tags: string[];
  score?: number;
  content_preview?: string;
  updated_at?: string;
}

export interface NotebookEvent {
  type: 'init' | 'step' | 'metric' | 'job_patch' | 'context_invalidated' | 'done' | 'error';
  notebook_id?: string;
  cursor?: number;
  job_id?: string;
  job_type?: string;
  step?: string;
  status?: string;
  progress?: number;
  message?: string;
  affected_note_ids?: string[];
  timestamp?: string;
  processed?: number;
  total?: number;
  value?: number;
  name?: string;
}

export interface NotebookWorkspaceData {
  generated_at: string;
  notebook: {
    id: string;
    name: string;
    description: string;
    color?: string;
    icon?: string;
    source_count?: number;
    note_count?: number;
    last_chat_at?: string | null;
    last_output_at?: string | null;
    default_kb_id?: string | null;
    auto_import_enabled?: boolean;
    created_at: string;
    updated_at: string;
  };
  sources: NotebookSource[];
  recent_sessions: NotebookChatSessionSummary[];
  studio_outputs: NotebookStudioOutput[];
  notes_summary: NotebookNoteSummary[];
  ui_defaults: {
    selected_source_ids: string[];
    active_session_id: string | null;
    active_output_id: string | null;
    active_note_id?: string | null;
    note_drawer_open: boolean;
  };
  rail: {
    notebooks: NotebookListRow[];
    kb_options: NotebookKbOption[];
    stats: {
      note_count: number;
      record_count: number;
      coverage_rate: number;
      avg_mastery_score: number;
    };
  };
  notes: WorkspaceNoteSummary[];
  active_note_summary: {
    id: string;
    title: string;
    tags: string[];
    source_label: string;
    mastery_score?: number;
    updated_at: string;
    has_ai_summary?: boolean;
    ai_summary?: string;
  } | null;
  insights_summary: {
    coverage: {
      papers_with_notes?: number;
      total_papers?: number;
      coverage_rate?: number;
    };
    mastery: {
      note_count?: number;
      avg_score?: number;
    };
    weak_topics_top_n: Array<{ concept: string; count: number }>;
    high_value_review_notes: Array<{ id: string; title: string; urgency: number; mastery_score: number }>;
    updated_at?: string;
  };
  active_jobs: NotebookJob[];
  view_state_defaults: {
    active_note_id: string | null;
    mobile_tab: 'sources' | 'notes' | 'write' | 'context';
    context_tab: 'insights' | 'graph' | 'related' | 'evidence';
    editor_mode: 'edit' | 'split' | 'preview';
  };
}

export class NotebookApiError extends Error {
  status: number;
  payload: unknown;

  constructor(message: string, status: number, payload: unknown) {
    super(message);
    this.name = 'NotebookApiError';
    this.status = status;
    this.payload = payload;
  }
}

async function unwrapResponse<T>(res: Response): Promise<T> {
  const text = await res.text();
  const payload = text ? JSON.parse(text) : {};
  if (!res.ok || payload?.success === false) {
    const detail =
      payload?.detail?.message ||
      payload?.detail?.error ||
      payload?.error ||
      payload?.detail ||
      payload?.message ||
      `Request failed (${res.status})`;
    throw new NotebookApiError(String(detail), res.status, payload);
  }
  return payload.data as T;
}

async function apiFetch<T>(input: string, init?: RequestInit): Promise<T> {
  const res = await fetch(input, init);
  return unwrapResponse<T>(res);
}

function normalizeNotebookRow(row: Partial<NotebookListRow>): NotebookListRow {
  return {
    id: String(row.id || ''),
    name: String(row.name || 'Untitled notebook'),
    description: String(row.description || ''),
    color: String(row.color || '#111827'),
    icon: String(row.icon || 'book'),
    source_count: Number(row.source_count || 0),
    note_count: Number(row.note_count || 0),
    last_chat_at: row.last_chat_at ? String(row.last_chat_at) : null,
    last_output_at: row.last_output_at ? String(row.last_output_at) : null,
    created_at: String(row.created_at || ''),
    updated_at: String(row.updated_at || ''),
    default_kb_id: row.default_kb_id ? String(row.default_kb_id) : null,
    auto_import_enabled: Boolean(row.auto_import_enabled),
    record_count: Number(row.record_count || 0),
  };
}

function citationToEvidence(citations: NotebookCitation[] = []) {
  return citations.map((citation) => ({
    id: `${citation.source_id}:${citation.index}`,
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

function noteSummaryToWorkspace(summary: NotebookNoteSummary): WorkspaceNoteSummary {
  const firstCitation = summary.citations[0];
  const evidence = citationToEvidence(summary.citations);
  return {
    id: summary.id,
    notebook_id: '',
    title: summary.title,
    tags: summary.tags,
    source: {
      type: summary.kind,
      file_name: firstCitation?.source_title,
      citation_count: summary.citations.length,
      evidence_links: evidence,
    },
    links_count: summary.citations.length,
    mastery_score: summary.kind === 'manual' ? 0 : 78,
    content_preview: summary.preview,
    created_at: summary.created_at,
    updated_at: summary.updated_at,
    source_label: firstCitation ? `${firstCitation.source_title} · ${firstCitation.locator}` : 'Manual note',
    ai_summary: summary.preview,
    has_ai_summary: Boolean(summary.preview),
    ai_summary_updated_at: summary.updated_at,
  };
}

function normalizeNoteDetail(detail: NotebookNoteDetail): NotebookNoteDetail {
  const firstCitation = detail.citations[0];
  const inferredType =
    detail.kind === 'saved_research'
      ? 'research'
      : detail.kind === 'saved_chat'
        ? 'manual'
        : detail.kind === 'saved_studio'
          ? 'manual'
          : 'manual';
  return {
    ...detail,
    source: detail.source || {
      type: inferredType,
      file_name: firstCitation?.source_title,
      file_id: firstCitation?.source_id,
      page:
        firstCitation?.locator && /^p\.(\d+)$/i.test(firstCitation.locator)
          ? Number(firstCitation.locator.replace(/^p\./i, ''))
          : undefined,
      citation_count: detail.citations.length,
      evidence_links: citationToEvidence(detail.citations),
    },
    ai_meta: detail.ai_meta || {
      summary: detail.content.slice(0, 140),
      suggested_tags: detail.tags,
    },
  };
}

function normalizeWorkspaceData(
  workspace: Omit<NotebookWorkspaceData, 'rail' | 'notes' | 'active_note_summary' | 'insights_summary' | 'active_jobs' | 'view_state_defaults'>
): NotebookWorkspaceData {
  const notebooks = [normalizeNotebookRow(workspace.notebook)];
  const notes = workspace.notes_summary.map(noteSummaryToWorkspace);
  const activeNote = notes[0] || null;
  return {
    ...workspace,
    rail: {
      notebooks,
      kb_options: workspace.notebook.default_kb_id
        ? [{ id: workspace.notebook.default_kb_id, name: 'Bound knowledge base' }]
        : [],
      stats: {
        note_count: workspace.notes_summary.length,
        record_count: workspace.sources.length,
        coverage_rate: workspace.sources.length > 0 ? workspace.notes_summary.length / workspace.sources.length : 0,
        avg_mastery_score: notes.length ? Math.round(notes.reduce((sum, note) => sum + (note.mastery_score || 0), 0) / notes.length) : 0,
      },
    },
    notes: notes.map((row) => ({ ...row, notebook_id: workspace.notebook.id })),
    active_note_summary: activeNote
      ? {
          id: activeNote.id,
          title: activeNote.title,
          tags: activeNote.tags,
          source_label: activeNote.source_label || 'Manual note',
          mastery_score: activeNote.mastery_score,
          updated_at: activeNote.updated_at,
          has_ai_summary: activeNote.has_ai_summary,
          ai_summary: activeNote.ai_summary,
        }
      : null,
    insights_summary: {
      coverage: {
        papers_with_notes: workspace.notes_summary.length,
        total_papers: workspace.sources.length,
        coverage_rate: workspace.sources.length > 0 ? workspace.notes_summary.length / workspace.sources.length : 0,
      },
      mastery: {
        note_count: workspace.notes_summary.length,
        avg_score: notes.length ? Math.round(notes.reduce((sum, note) => sum + (note.mastery_score || 0), 0) / notes.length) : 0,
      },
      weak_topics_top_n: [],
      high_value_review_notes: [],
      updated_at: workspace.generated_at,
    },
    active_jobs: [],
    view_state_defaults: {
      active_note_id: workspace.ui_defaults.active_note_id || workspace.notes_summary[0]?.id || null,
      mobile_tab: 'write',
      context_tab: 'insights',
      editor_mode: 'edit',
    },
  };
}

export function listNotebooks(): Promise<NotebookListRow[]> {
  return apiFetch<NotebookListRow[]>('/api/notebooks').then((rows) => rows.map((row) => normalizeNotebookRow(row)));
}

export function getNotebookWorkspace(
  notebookId: string,
  params?: { activeNoteId?: string | null; search?: string; tag?: string }
): Promise<NotebookWorkspaceData> {
  const qs = new URLSearchParams();
  if (params?.activeNoteId) qs.set('active_note_id', params.activeNoteId);
  if (params?.search?.trim()) qs.set('search', params.search.trim());
  if (params?.tag?.trim()) qs.set('tag', params.tag.trim());
  const suffix = qs.toString() ? `?${qs.toString()}` : '';
  return apiFetch<NotebookWorkspaceData>(`/api/notebooks/${notebookId}/workspace${suffix}`).then((data) =>
    normalizeWorkspaceData(data)
  );
}

export function createNotebook(payload: {
  name: string;
  description?: string;
  color?: string;
  icon?: string;
  default_kb_id?: string | null;
  auto_import_enabled?: boolean;
}): Promise<NotebookListRow> {
  return apiFetch<NotebookListRow>('/api/notebooks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then((row) => normalizeNotebookRow(row));
}

export function updateNotebook(
  notebookId: string,
  payload: Partial<
    Pick<NotebookListRow, 'name' | 'description' | 'color' | 'icon' | 'default_kb_id' | 'auto_import_enabled'>
  >
): Promise<NotebookListRow> {
  return apiFetch<NotebookListRow>(`/api/notebooks/${notebookId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then((row) => normalizeNotebookRow(row));
}

export async function deleteNotebook(notebookId: string): Promise<void> {
  await apiFetch<boolean>(`/api/notebooks/${notebookId}`, { method: 'DELETE' });
}

export type CreateNotebookSourcePayload =
  | { kind: 'pdf'; title?: string; file: File }
  | { kind: 'url'; title?: string; url: string }
  | { kind: 'text'; title?: string; text: string }
  | { kind: 'kb_ref'; title?: string; kb_id: string; file_id: string };

export function listNotebookSources(notebookId: string): Promise<NotebookSource[]> {
  return apiFetch<NotebookSource[]>(`/api/notebooks/${notebookId}/sources`);
}

export function createNotebookSource(
  notebookId: string,
  payload: CreateNotebookSourcePayload
): Promise<NotebookSource> {
  const body = new FormData();
  body.set('kind', payload.kind);
  if (payload.title?.trim()) body.set('title', payload.title.trim());
  if (payload.kind === 'pdf') {
    body.set('file', payload.file);
  }
  if (payload.kind === 'url') {
    body.set('url', payload.url);
  }
  if (payload.kind === 'text') {
    body.set('text', payload.text);
  }
  if (payload.kind === 'kb_ref') {
    body.set('kb_id', payload.kb_id);
    body.set('file_id', payload.file_id);
  }
  return apiFetch<NotebookSource>(`/api/notebooks/${notebookId}/sources`, {
    method: 'POST',
    body,
  });
}

export function updateNotebookSource(
  notebookId: string,
  sourceId: string,
  payload: { included?: boolean; title?: string }
): Promise<NotebookSource> {
  return apiFetch<NotebookSource>(`/api/notebooks/${notebookId}/sources/${sourceId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export async function deleteNotebookSource(notebookId: string, sourceId: string): Promise<void> {
  await apiFetch<boolean>(`/api/notebooks/${notebookId}/sources/${sourceId}`, { method: 'DELETE' });
}

export function listNotebookChatSessions(notebookId: string): Promise<NotebookChatSessionSummary[]> {
  return apiFetch<NotebookChatSessionSummary[]>(`/api/notebooks/${notebookId}/chat/sessions`);
}

export function createNotebookChatSession(
  notebookId: string,
  payload: { title?: string }
): Promise<NotebookChatSessionDetail> {
  return apiFetch<NotebookChatSessionDetail>(`/api/notebooks/${notebookId}/chat/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function getNotebookChatSession(
  notebookId: string,
  sessionId: string
): Promise<NotebookChatSessionDetail> {
  return apiFetch<NotebookChatSessionDetail>(`/api/notebooks/${notebookId}/chat/sessions/${sessionId}`);
}

export async function streamNotebookChat(
  notebookId: string,
  payload: { session_id?: string | null; message: string; source_ids?: string[] },
  handlers: {
    onChunk?: (chunk: string) => void;
    onCitations?: (citations: NotebookCitation[]) => void;
    onBackgroundExtension?: (content: string) => void;
  } = {}
): Promise<{ session: NotebookChatSessionDetail; assistant_message: NotebookChatMessage }> {
  const res = await fetch(`/api/notebooks/${notebookId}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    await unwrapResponse(res);
  }
  if (!res.body) {
    throw new NotebookApiError('Chat stream unavailable', res.status, null);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let finalSession: NotebookChatSessionDetail | null = null;
  let finalAssistant: NotebookChatMessage | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const payloadText = line.slice(6).trim();
      if (!payloadText) continue;
      const event = JSON.parse(payloadText) as Record<string, unknown>;
      if (event.type === 'message_chunk') {
        handlers.onChunk?.(String(event.content || ''));
      } else if (event.type === 'citations') {
        handlers.onCitations?.((event.data || []) as NotebookCitation[]);
      } else if (event.type === 'background_extension') {
        handlers.onBackgroundExtension?.(String(event.content || ''));
      } else if (event.type === 'done') {
        finalSession = event.session as NotebookChatSessionDetail;
        finalAssistant = event.assistant_message as NotebookChatMessage;
      } else if (event.type === 'error') {
        throw new NotebookApiError(String(event.error || 'Notebook chat failed'), res.status, event);
      }
    }
  }

  if (!finalSession || !finalAssistant) {
    throw new NotebookApiError('Notebook chat ended without final payload', res.status, null);
  }
  return { session: finalSession, assistant_message: finalAssistant };
}

export function listNotebookStudioOutputs(notebookId: string): Promise<NotebookStudioOutput[]> {
  return apiFetch<NotebookStudioOutput[]>(`/api/notebooks/${notebookId}/studio`);
}

export function generateNotebookStudioOutput(
  notebookId: string,
  payload: { kind: NotebookStudioOutput['kind']; source_ids?: string[]; session_id?: string | null }
): Promise<NotebookStudioOutput> {
  return apiFetch<NotebookStudioOutput>(`/api/notebooks/${notebookId}/studio`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export async function deleteNotebookStudioOutput(notebookId: string, outputId: string): Promise<void> {
  await apiFetch<boolean>(`/api/notebooks/${notebookId}/studio/${outputId}`, { method: 'DELETE' });
}

export function saveStudioOutputAsNote(
  notebookId: string,
  outputId: string
): Promise<NotebookNoteDetail> {
  return apiFetch<NotebookNoteDetail>(`/api/notebooks/${notebookId}/studio/${outputId}/save-note`, {
    method: 'POST',
  }).then((detail) => normalizeNoteDetail(detail));
}

export function listNotebookNotes(
  notebookId: string,
  params?: { search?: string; tag?: string }
): Promise<NotebookNoteSummary[]> {
  const qs = new URLSearchParams();
  if (params?.search?.trim()) qs.set('search', params.search.trim());
  if (params?.tag?.trim()) qs.set('tag', params.tag.trim());
  const suffix = qs.toString() ? `?${qs.toString()}` : '';
  return apiFetch<NotebookNoteSummary[]>(`/api/notebooks/${notebookId}/notes${suffix}`);
}

export function getNoteDetail(notebookId: string, noteId: string): Promise<NotebookNoteDetail> {
  return apiFetch<NotebookNoteDetail>(`/api/notebooks/${notebookId}/notes/${noteId}`).then((detail) =>
    normalizeNoteDetail(detail)
  );
}

export function createNote(
  notebookId: string,
  payload: {
    title: string;
    content: string;
    kind?: NotebookNoteDetail['kind'];
    origin?: string | null;
    citations?: NotebookCitation[];
    source_ids?: string[];
    tags?: string[];
    source?: { type: string };
  }
): Promise<NotebookNoteDetail> {
  return apiFetch<NotebookNoteDetail>(`/api/notebooks/${notebookId}/notes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title: payload.title,
      content: payload.content,
      kind: payload.kind || (payload.source?.type === 'manual' ? 'manual' : 'manual'),
      origin: payload.origin || null,
      citations: payload.citations || [],
      source_ids: payload.source_ids || [],
      tags: payload.tags || [],
    }),
  }).then((detail) => normalizeNoteDetail(detail));
}

export async function updateNote(
  notebookId: string,
  noteId: string,
  payload: {
    title?: string;
    content?: string;
    kind?: NotebookNoteDetail['kind'];
    origin?: string | null;
    citations?: NotebookCitation[];
    source_ids?: string[];
    tags?: string[];
    expected_updated_at?: string;
  }
): Promise<NotebookNoteDetail> {
  return apiFetch<NotebookNoteDetail>(`/api/notebooks/${notebookId}/notes/${noteId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then((detail) => normalizeNoteDetail(detail));
}

export async function deleteNote(notebookId: string, noteId: string): Promise<void> {
  await apiFetch<boolean>(`/api/notebooks/${notebookId}/notes/${noteId}`, { method: 'DELETE' });
}

export function saveNotebookNoteFromSources(
  notebookId: string,
  payload: {
    title: string;
    content: string;
    sources: Array<Record<string, unknown>>;
    kb_id?: string;
    origin_type: 'research' | 'co_writer' | 'chat' | 'studio';
    tags?: string[];
  }
): Promise<NotebookNoteDetail> {
  return apiFetch<NotebookNoteDetail>(`/api/notebooks/${notebookId}/notes/from-sources`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then((detail) => normalizeNoteDetail(detail));
}

export function getGraphView(notebookId: string, refresh = false): Promise<GraphViewPayload> {
  const suffix = refresh ? '?refresh=true' : '';
  return apiFetch<GraphViewPayload>(`/api/notebooks/${notebookId}/graph-view${suffix}`);
}

export function getRelatedNotes(notebookId: string, noteId: string): Promise<RelatedNote[]> {
  return apiFetch<RelatedNote[]>(
    `/api/notebooks/${notebookId}/notes/${noteId}/related?limit=8&include_all=true&min_score=0.15`
  );
}

export function getNoteMeta(notebookId: string, noteId: string): Promise<NotebookNoteMeta> {
  return apiFetch<NotebookNoteMeta>(`/api/notebooks/${notebookId}/notes/${noteId}/meta`);
}

export async function updateNoteMeta(
  notebookId: string,
  noteId: string,
  payload: Partial<NotebookNoteMeta>
): Promise<NotebookNoteMeta> {
  return apiFetch<NotebookNoteMeta>(`/api/notebooks/${notebookId}/notes/${noteId}/meta`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function startNotebookImport(
  notebookId: string,
  kbId: string
): Promise<{
  id: string;
  status: 'pending' | 'running' | 'done' | 'partial_failed';
  progress: number;
  processed: number;
  total: number;
  note_ids?: string[];
}> {
  return apiFetch(`/api/notebooks/${notebookId}/imports/kb`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      kb_id: kbId,
      trigger_mode: 'manual',
      run_async: true,
    }),
  });
}

export function rerunExtraction(
  notebookId: string,
  noteId: string
): Promise<{ job_id?: string; note: NotebookNoteDetail; meta?: NotebookNoteMeta }> {
  return apiFetch(`/api/notebooks/${notebookId}/notes/${noteId}/extract`, {
    method: 'POST',
  });
}

export async function migrateNotebookRecords(notebookId: string): Promise<{ migrated_count: number }> {
  return apiFetch(`/api/notebooks/${notebookId}/migrate-records`, {
    method: 'POST',
  });
}
