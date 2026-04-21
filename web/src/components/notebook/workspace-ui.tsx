'use client';

import type { CSSProperties, ReactNode, KeyboardEvent as ReactKeyboardEvent } from 'react';
import {
  ArrowLeft,
  BookOpen,
  Bot,
  ChevronRight,
  Ellipsis,
  FileText,
  Plus,
  Send,
  Sparkles,
  Trash2,
} from 'lucide-react';

import MarkdownRenderer from '@/components/MarkdownRenderer';
import EvidenceCard from '@/components/common/EvidenceCard';
import type { NotebookChatMessage, NotebookChatSessionSummary, NotebookNoteDetail, NotebookNoteSummary, NotebookSource } from '@/lib/notebook-api';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';

export const NOTEBOOK_THEME_STYLES: CSSProperties & Record<string, string> = {
  '--nb-page-bg': '#F3F5F9',
  '--nb-surface': '#FFFFFF',
  '--nb-surface-muted': '#F7F8FB',
  '--nb-surface-soft': '#FBFCFE',
  '--nb-border': '#E4E8F0',
  '--nb-border-soft': '#EDF1F6',
  '--nb-text-strong': '#161B26',
  '--nb-text': '#596579',
  '--nb-text-soft': '#8A94A7',
  '--nb-primary': '#111111',
  '--nb-primary-soft': '#EEF2F8',
  '--nb-panel-radius': '24px',
  '--nb-card-radius': '18px',
  '--nb-input-radius': '20px',
  '--nb-button-radius': '14px',
};

export const notebookUi = {
  page: 'min-h-screen bg-[var(--nb-page-bg)] px-4 py-4 sm:px-5 sm:py-5 lg:h-screen lg:overflow-hidden',
  pageWrap: 'mx-auto flex min-h-[calc(100vh-2rem)] max-w-[1800px] flex-col gap-4 lg:h-[calc(100vh-2.5rem)] lg:min-h-0',
  panel:
    'overflow-hidden rounded-[var(--nb-panel-radius)] border border-[var(--nb-border)] bg-[var(--nb-surface)] shadow-[0_1px_2px_rgba(17,24,39,0.03)]',
  headerButton:
    'h-10 rounded-[var(--nb-button-radius)] border-[var(--nb-border)] bg-[var(--nb-surface)] px-4 text-[13px] font-medium text-[var(--nb-text-strong)] shadow-none hover:bg-[var(--nb-surface-muted)]',
  primaryButton:
    'h-10 rounded-[var(--nb-button-radius)] bg-[var(--nb-primary)] px-4 text-[13px] font-medium text-white shadow-none hover:bg-[#202020]',
  secondaryBadge:
    'inline-flex items-center gap-1 rounded-full border border-[var(--nb-border-soft)] bg-[var(--nb-surface-soft)] px-2.5 py-1 text-[11px] font-medium text-[var(--nb-text)]',
  panelHeader: 'flex min-h-[52px] items-center justify-between gap-3 border-b border-[var(--nb-border)] px-4 py-3',
  subHeader: 'text-[11px] leading-4 text-[var(--nb-text)]',
  sectionTitle: 'text-[16px] font-semibold text-[var(--nb-text-strong)]',
};

type MobileTab = 'sources' | 'chat' | 'notes';

function stripExtension(name: string): string {
  return name.replace(/\.[^.]+$/, '');
}

function sourceDisplayTitle(source: NotebookSource): string {
  const fileName = typeof source.metadata?.file_name === 'string' ? source.metadata.file_name.trim() : '';
  if (source.kind === 'kb_ref' && fileName) {
    return stripExtension(fileName);
  }
  return source.title || (fileName ? stripExtension(fileName) : 'Untitled source');
}

export function NotebookHeader({
  title,
  sourceCount,
  noteCount,
  onAddSource,
  onAddNote,
}: {
  title: string;
  sourceCount: number;
  noteCount: number;
  onAddSource: () => void;
  onAddNote: () => void;
}) {
  return (
    <header className={notebookUi.panel}>
      <div className="flex min-h-[52px] flex-wrap items-center justify-between gap-3 px-4 py-2 sm:px-5">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[14px] border border-[var(--nb-border-soft)] bg-[var(--nb-surface-muted)] text-[var(--nb-text-strong)]">
            <BookOpen className="h-[16px] w-[16px]" />
          </div>
          <h1 className="truncate text-[20px] leading-[26px] font-semibold tracking-[-0.02em] text-[var(--nb-text-strong)] sm:text-[22px]">
            {title}
          </h1>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className="hidden items-center gap-2 rounded-full border border-[var(--nb-border)] bg-[var(--nb-surface)] px-3.5 py-2 text-[12px] leading-4 text-[var(--nb-text)] sm:flex">
            <span>{sourceCount} 个来源</span>
            <span className="text-[var(--nb-text-soft)]">/</span>
            <span>{noteCount} 条笔记</span>
          </div>
          <Button variant="outline" className={notebookUi.headerButton} onClick={onAddSource} data-testid="notebook-add-source">
            <Plus className="h-4 w-4" />
            Add sources
          </Button>
          <Button className={notebookUi.primaryButton} onClick={onAddNote} data-testid="notebook-open-notes">
            <Plus className="h-4 w-4" />
            New note
          </Button>
        </div>
      </div>
    </header>
  );
}

export function MobileTabs({
  mobileTab,
  setMobileTab,
}: {
  mobileTab: MobileTab;
  setMobileTab: (tab: MobileTab) => void;
}) {
  return (
    <div className="lg:hidden">
      <div className="grid grid-cols-3 gap-1.5 rounded-[20px] border border-[var(--nb-border)] bg-[var(--nb-surface)] p-1.5">
        {[
          { key: 'sources' as const, label: 'Sources' },
          { key: 'chat' as const, label: 'Chat' },
          { key: 'notes' as const, label: 'Notes' },
        ].map((tab) => (
          <button
            key={tab.key}
            type="button"
            className={cn(
              'h-10 rounded-[14px] px-3 text-[13px] font-medium text-[var(--nb-text)] transition-colors',
              mobileTab === tab.key && 'bg-[var(--nb-surface-muted)] text-[var(--nb-text-strong)]'
            )}
            onClick={() => setMobileTab(tab.key)}
            data-testid={`mobile-tab-${tab.key}`}
          >
            {tab.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function SourceTypeBadge({ kind }: { kind: NotebookSource['kind'] }) {
  const labelMap: Record<NotebookSource['kind'], string> = {
    pdf: 'PDF',
    url: '网页',
    text: '文本',
    kb_ref: '知识库',
  };
  return <span className={notebookUi.secondaryBadge}>{labelMap[kind]}</span>;
}

export function SourceListItem({
  source,
  selected,
  onToggleSelected,
  onDelete,
}: {
  source: NotebookSource;
  selected: boolean;
  onToggleSelected: () => void;
  onDelete: () => void;
}) {
  const displayTitle = sourceDisplayTitle(source);

  return (
    <div
      className={cn(
        'group flex items-center gap-3 overflow-hidden rounded-[16px] border px-3 py-3 transition-colors',
        selected
          ? 'border-[#D8E0EC] bg-[var(--nb-primary-soft)]'
          : 'border-transparent bg-[var(--nb-surface)] hover:border-[var(--nb-border)] hover:bg-[var(--nb-surface-muted)]'
      )}
    >
      <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-3 overflow-hidden">
        <input
          type="checkbox"
          checked={selected}
          onChange={onToggleSelected}
          className="h-4 w-4 rounded border-[var(--nb-border)] text-[var(--nb-primary)] focus:ring-[var(--nb-primary)]"
        />
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[12px] border border-[var(--nb-border-soft)] bg-[var(--nb-surface-soft)] text-[var(--nb-text)]">
          <FileTextIcon kind={source.kind} />
        </div>
        <div className="min-w-0 flex-1 overflow-hidden">
          <div className="block w-full truncate overflow-hidden text-[15px] font-semibold whitespace-nowrap text-[var(--nb-text-strong)]">
            {displayTitle}
          </div>
        </div>
      </label>
      <button
        type="button"
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] text-[var(--nb-text-soft)] opacity-0 transition group-hover:opacity-100 hover:bg-[var(--nb-surface)] hover:text-[var(--nb-text-strong)]"
        onClick={onDelete}
      >
        <Trash2 className="h-4 w-4" />
      </button>
    </div>
  );
}

function FileTextIcon({ kind }: { kind: NotebookSource['kind'] }) {
  const shared = 'h-4 w-4';
  if (kind === 'url') return <ChevronRight className={shared} />;
  if (kind === 'kb_ref') return <BookOpen className={shared} />;
  return <BookOpen className={shared} />;
}

export function SourcesPanel({
  sources,
  selectedCount,
  allSelected,
  onSelectAll,
  onAddSource,
  onToggleSource,
  onDeleteSource,
  mobileHidden,
}: {
  sources: NotebookSource[];
  selectedCount: number;
  allSelected: boolean;
  onSelectAll: () => void;
  onAddSource: () => void;
  onToggleSource: (source: NotebookSource) => void;
  onDeleteSource: (sourceId: string) => void;
  mobileHidden: boolean;
}) {
  return (
    <section
      data-testid="notebook-sources-panel"
      className={cn(notebookUi.panel, 'min-h-[34rem] lg:min-h-0', mobileHidden && 'hidden lg:block')}
    >
      <div className="flex h-full min-h-0 flex-col">
        <div className={notebookUi.panelHeader}>
          <div>
            <div className={notebookUi.sectionTitle}>Sources</div>
            <div className={notebookUi.subHeader}>把资料组织成可控的来源范围</div>
          </div>
          <button
            type="button"
            className="flex h-9 w-9 items-center justify-center rounded-[14px] border border-[var(--nb-border)] bg-[var(--nb-surface)] text-[var(--nb-text)] transition-colors hover:bg-[var(--nb-surface-muted)] hover:text-[var(--nb-text-strong)]"
            onClick={onAddSource}
          >
            <Plus className="h-4 w-4" />
          </button>
        </div>

        <div className="border-b border-[var(--nb-border)] px-4 py-3" data-testid="sources-select-all">
          <label className="flex cursor-pointer items-center justify-between gap-3 rounded-[14px] bg-[var(--nb-surface-soft)] px-3 py-2.5">
            <span className="text-[13px] font-medium text-[var(--nb-text-strong)]">Select all sources</span>
            <span className="flex items-center gap-3 text-[12px] text-[var(--nb-text-soft)]">
              <span>
                {selectedCount}/{sources.length}
              </span>
              <input
                type="checkbox"
                checked={allSelected}
                onChange={onSelectAll}
                className="h-4 w-4 rounded border-[var(--nb-border)] text-[var(--nb-primary)] focus:ring-[var(--nb-primary)]"
              />
            </span>
          </label>
        </div>

        <ScrollArea className="min-h-0 flex-1 px-4 py-4">
          <div className="space-y-2">
            {sources.length === 0 ? (
              <div className="rounded-[18px] border border-dashed border-[var(--nb-border-soft)] bg-[var(--nb-surface-muted)] px-5 py-8 text-center">
                <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-[16px] border border-[var(--nb-border-soft)] bg-[var(--nb-surface)] text-[var(--nb-text-strong)]">
                  <BookOpen className="h-5 w-5" />
                </div>
                <div className="mt-4 text-[18px] font-semibold text-[var(--nb-text-strong)]">还没有来源</div>
                <p className="mx-auto mt-2 max-w-[16rem] text-[13px] leading-6 text-[var(--nb-text)]">
                  加入 PDF、网页、文本或知识库文件后，左栏会整理成更轻量的资料列表。
                </p>
                <Button className={cn(notebookUi.primaryButton, 'mt-5')} onClick={onAddSource}>
                  <Plus className="h-4 w-4" />
                  添加第一个来源
                </Button>
              </div>
            ) : (
              sources.map((source) => (
                <SourceListItem
                  key={source.id}
                  source={source}
                  selected={source.included}
                  onToggleSelected={() => onToggleSource(source)}
                  onDelete={() => onDeleteSource(source.id)}
                />
              ))
            )}
          </div>
        </ScrollArea>
      </div>
    </section>
  );
}

export function ChatShell({
  headerStatus,
  body,
  composer,
  mobileHidden,
}: {
  headerStatus: ReactNode;
  body: ReactNode;
  composer: ReactNode;
  mobileHidden: boolean;
}) {
  return (
    <section
      data-testid="notebook-chat-panel"
      className={cn(notebookUi.panel, 'min-h-[34rem] lg:min-h-0', mobileHidden && 'hidden lg:block')}
    >
      <div className="flex h-full min-h-0 flex-col">
        <div className={notebookUi.panelHeader}>
          <div>
            <div className={notebookUi.sectionTitle}>Chat</div>
            <div className={notebookUi.subHeader}>围绕已选来源进行问答与沉淀</div>
          </div>
          <div className="flex items-center gap-2">{headerStatus}</div>
        </div>
        <div className="min-h-0 flex-1">{body}</div>
        {composer}
      </div>
    </section>
  );
}

export function ChatEmptyState({
  notebookName,
  sourceCount,
  description,
  prompts,
  onPromptClick,
}: {
  notebookName: string;
  sourceCount: number;
  description?: string | null;
  prompts: string[];
  onPromptClick: (prompt: string) => void;
}) {
  return (
    <div data-testid="notebook-chat-empty-state" className="mx-auto flex h-full w-full max-w-3xl flex-col items-center justify-center px-8 py-12 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-[20px] border border-[var(--nb-border-soft)] bg-[var(--nb-surface-muted)] text-[var(--nb-text-strong)]">
        <Bot className="h-6 w-6" />
      </div>
      <div className="mt-5 text-[34px] font-semibold tracking-[-0.03em] text-[var(--nb-text-strong)]">{notebookName}</div>
      <div className="mt-2 text-[13px] text-[var(--nb-text-soft)]">{sourceCount} sources</div>
      <p className="mt-6 max-w-2xl text-[16px] leading-8 text-[var(--nb-text)]">
        {description || '把来源组织进来之后，这里会像 Notebook 工作台一样，围绕资料做 grounded chat、总结与长期笔记沉淀。'}
      </p>
      <div className="mt-8 flex flex-wrap justify-center gap-2.5">
        {prompts.map((prompt) => (
          <button
            key={prompt}
            type="button"
            className="rounded-full border border-[var(--nb-border)] bg-[var(--nb-surface)] px-4 py-2 text-[13px] font-medium text-[var(--nb-text)] transition-colors hover:bg-[var(--nb-surface-muted)] hover:text-[var(--nb-text-strong)]"
            onClick={() => onPromptClick(prompt)}
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
}

export function ChatInput({
  enabledSources,
  composer,
  onComposerChange,
  onKeyDown,
  onSend,
  sending,
}: {
  enabledSources: NotebookSource[];
  composer: string;
  onComposerChange: (value: string) => void;
  onKeyDown: (event: ReactKeyboardEvent<HTMLTextAreaElement>) => void;
  onSend: () => void;
  sending: boolean;
}) {
  return (
    <div className="border-t border-[var(--nb-border)] px-5 py-4">
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
          <span className="rounded-full bg-[#FFF4E6] px-2.5 py-1 text-[12px] text-[#B56A20]">当前没有启用来源</span>
        )}
      </div>
      <div className="flex items-end gap-3 rounded-[24px] border border-[var(--nb-border)] bg-[var(--nb-surface)] px-4 py-3">
        <textarea
          value={composer}
          onChange={(event) => onComposerChange(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Start typing..."
          className="min-h-[56px] max-h-40 flex-1 resize-none bg-transparent py-1 text-[15px] leading-7 text-[var(--nb-text-strong)] outline-none placeholder:text-[var(--nb-text-soft)]"
          data-testid="notebook-chat-input"
        />
        <button
          type="button"
          className="flex h-11 w-11 items-center justify-center rounded-full bg-[var(--nb-primary)] text-white transition-colors hover:bg-[#222222] disabled:cursor-not-allowed disabled:bg-[#9DA3AF]"
          onClick={onSend}
          disabled={sending || !composer.trim()}
          data-testid="notebook-chat-send"
        >
          {sending ? <Sparkles className="h-4 w-4 animate-pulse" /> : <Send className="h-4 w-4" />}
        </button>
      </div>
    </div>
  );
}

export function NoteListItem({
  note,
  active,
  onClick,
}: {
  note: NotebookNoteSummary;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      data-testid="note-list-item"
      type="button"
      className={cn(
        'w-full overflow-hidden rounded-[18px] border px-4 py-3.5 text-left transition-colors',
        active
          ? 'border-[#D8E0EC] bg-[#EEF1F6]'
          : 'border-transparent bg-[var(--nb-surface)] hover:border-[var(--nb-border)] hover:bg-[var(--nb-surface-muted)]'
      )}
      onClick={onClick}
    >
      <div className="flex items-center gap-3 overflow-hidden">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[14px] bg-[#F3F4F6] text-[#8A6F2A]">
          <FileText className="h-[18px] w-[18px]" />
        </div>
        <div className="min-w-0 flex-1 overflow-hidden">
          <div
            className="block w-full truncate overflow-hidden whitespace-nowrap text-[15px] font-semibold text-[var(--nb-text-strong)]"
            data-testid="note-list-item-title"
          >
            {note.title}
          </div>
        </div>
        <span aria-hidden="true" className="shrink-0 text-[var(--nb-text-soft)]">
          <Ellipsis className="h-4 w-4" />
        </span>
      </div>
    </button>
  );
}

export function NoteReadingView({
  activeNote,
  formatDateTime,
  children,
}: {
  activeNote: NotebookNoteDetail;
  formatDateTime: (value?: string | null) => string;
  children?: ReactNode;
}) {
  const noteTypeLabel =
    activeNote.kind === 'saved_studio'
      ? 'Report'
      : activeNote.kind === 'saved_chat'
        ? 'Chat'
        : activeNote.kind === 'saved_research'
          ? 'Legacy note'
          : 'Note';

  return (
    <div data-testid="note-reading-view" className="space-y-5">
      <div className="space-y-4">
        <div
          className="flex items-center gap-2 text-[13px] font-medium text-[var(--nb-text-strong)]"
          data-testid="note-reading-breadcrumb"
        >
          <span>Notes</span>
          <ChevronRight className="h-4 w-4 text-[var(--nb-text-soft)]" />
          <span>{noteTypeLabel}</span>
        </div>
        <div className="space-y-2">
          <div
            className="text-[24px] leading-[1.2] font-semibold tracking-[-0.02em] text-[var(--nb-text-strong)]"
            data-testid="note-reading-title"
          >
            {activeNote.title}
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[14px] text-[var(--nb-text)]">
            <span data-testid="note-reading-source-count">Based on {activeNote.source_ids.length} sources</span>
            <span className="text-[var(--nb-text-soft)]">·</span>
            <span>{formatDateTime(activeNote.updated_at)}</span>
          </div>
        </div>
      </div>

      <div className="border-t border-[var(--nb-border)] pt-6">
        <MarkdownRenderer
          className="max-w-none text-[var(--nb-text-strong)] prose prose-slate prose-headings:mb-4 prose-headings:text-[var(--nb-text-strong)] prose-h1:text-[24px] prose-h1:leading-[1.2] prose-h2:text-[20px] prose-h2:leading-[1.3] prose-p:text-[14px] prose-p:leading-7 prose-p:text-[var(--nb-text-strong)] prose-li:text-[14px] prose-li:leading-7 prose-li:text-[var(--nb-text-strong)] prose-strong:text-[var(--nb-text-strong)] prose-em:text-[var(--nb-text-strong)]"
          content={activeNote.content || '暂无正文内容'}
        />
      </div>
      {children}
    </div>
  );
}

export function NotesPanel({
  notes,
  activeNoteId,
  notesList,
  detailHeader,
  detailBody,
  onBackToList,
  onGenerateReport,
  onNewNote,
  reportGenerating,
  mobileHidden,
}: {
  notes: NotebookNoteSummary[];
  activeNoteId: string | null;
  notesList: ReactNode;
  detailHeader: ReactNode;
  detailBody: ReactNode;
  onBackToList: () => void;
  onGenerateReport: () => void;
  onNewNote: () => void;
  reportGenerating: boolean;
  mobileHidden: boolean;
}) {
  const showDetail = Boolean(activeNoteId);

  return (
    <section
      data-testid="notebook-notes-panel"
      className={cn(notebookUi.panel, 'min-h-[34rem] lg:min-h-0', mobileHidden && 'hidden lg:block')}
    >
      <div className="flex h-full min-h-0 flex-col">
        <div className={notebookUi.panelHeader}>
          <div className={notebookUi.sectionTitle}>Notes</div>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              className={cn(notebookUi.headerButton, 'h-9 px-3')}
              onClick={onGenerateReport}
              disabled={reportGenerating}
              data-testid="notebook-generate-report"
            >
              {reportGenerating ? <Sparkles className="h-4 w-4 animate-pulse" /> : <Sparkles className="h-4 w-4" />}
              生成报告
            </Button>
            <Button size="sm" className={cn(notebookUi.primaryButton, 'h-9 px-3')} onClick={onNewNote}>
              <Plus className="h-4 w-4" />
              新建
            </Button>
          </div>
        </div>

        <div className="min-h-0 flex-1 px-4 pb-4 pt-4">
          {showDetail ? (
            <div className="flex h-full min-h-0 flex-col rounded-[20px] border border-[var(--nb-border)] bg-[var(--nb-surface)]">
              <div className="flex items-center justify-between gap-3 border-b border-[var(--nb-border)] px-5 py-3.5">
                <button
                  type="button"
                  onClick={onBackToList}
                  className="inline-flex h-9 items-center gap-2 rounded-[14px] border border-[var(--nb-border)] bg-[var(--nb-surface)] px-3 text-[13px] font-medium text-[var(--nb-text-strong)] transition-colors hover:bg-[var(--nb-surface-muted)]"
                  data-testid="notes-back-to-list"
                >
                  <ArrowLeft className="h-4 w-4" />
                  Notes
                </button>
                <div className="min-w-0 flex-1">{detailHeader}</div>
              </div>
              <ScrollArea className="min-h-0 flex-1 px-5 py-5">{detailBody}</ScrollArea>
            </div>
          ) : (
            <div className="h-full min-h-0 rounded-[20px] border border-[var(--nb-border)] bg-[var(--nb-surface)]">
              <ScrollArea className="h-full px-3 py-3">
                {notes.length > 0 ? notesList : <div className="px-3 py-4 text-[13px] text-[var(--nb-text)]">这里还没有保存的笔记。</div>}
              </ScrollArea>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
