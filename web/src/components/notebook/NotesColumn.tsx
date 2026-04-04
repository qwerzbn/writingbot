'use client';

import { useMemo } from 'react';
import { Loader2, Plus, Search, StickyNote, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { CollapsibleColumn, createCollapseButton } from '@/components/notebook/CollapsibleColumn';
import { useNotebookColumnsStore } from '@/lib/stores/notebook-columns-store';

interface NoteSummary {
  id: string;
  title: string;
  source: {
    type?: string;
    file_name?: string;
  };
  tags: string[];
  mastery_score?: number;
  links_count?: number;
}

interface NotesColumnProps {
  notes: NoteSummary[];
  loading: boolean;
  selectedNoteId: string | null;
  search: string;
  tag: string;
  disabled?: boolean;
  onSearchChange: (value: string) => void;
  onTagChange: (value: string) => void;
  onSelectNote: (id: string) => void;
  onCreateNote: () => void;
  onDeleteNote: (id: string) => void;
}

export default function NotesColumn({
  notes,
  loading,
  selectedNoteId,
  search,
  tag,
  disabled,
  onSearchChange,
  onTagChange,
  onSelectNote,
  onCreateNote,
  onDeleteNote,
}: NotesColumnProps) {
  const { notesCollapsed, toggleNotes } = useNotebookColumnsStore();
  const collapseButton = useMemo(() => createCollapseButton(toggleNotes, '笔记'), [toggleNotes]);

  return (
    <CollapsibleColumn
      isCollapsed={notesCollapsed}
      onToggle={toggleNotes}
      collapsedIcon={StickyNote}
      collapsedLabel="笔记"
    >
      <Card className="flex h-full flex-col gap-0 py-0" data-testid="notebook-notes-column">
        <CardHeader className="border-b py-3">
          <div className="flex items-center justify-between gap-2">
            <CardTitle className="text-sm">笔记列表</CardTitle>
            <div className="flex items-center gap-1">
              <Button size="sm" disabled={disabled} onClick={onCreateNote} className="h-8" data-testid="notebook-create-note">
                <Plus className="h-3.5 w-3.5" />
                新建
              </Button>
              {collapseButton}
            </div>
          </div>
          <div className="mt-2 space-y-2">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
              <input
                value={search}
                onChange={(e) => onSearchChange(e.target.value)}
                placeholder="搜索笔记"
                className="h-9 w-full rounded-md border bg-background pl-7 pr-2 text-xs"
                data-testid="notebook-search-input"
              />
            </div>
            <input
              value={tag}
              onChange={(e) => onTagChange(e.target.value)}
              placeholder="标签筛选"
              className="h-9 w-full rounded-md border bg-background px-2 text-xs"
              data-testid="notebook-tag-input"
            />
          </div>
        </CardHeader>

        <CardContent className="min-h-0 flex-1 px-0">
          {loading ? (
            <div className="flex items-center gap-2 px-4 py-3 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              加载笔记
            </div>
          ) : notes.length === 0 ? (
            <div className="px-4 py-6 text-sm text-muted-foreground">暂无笔记，可新建或导入卡片。</div>
          ) : (
            <ScrollArea className="h-full">
              <div className="px-2 py-2">
                {notes.map((note) => {
                  const active = selectedNoteId === note.id;
                  return (
                    <button
                      key={note.id}
                      onClick={() => onSelectNote(note.id)}
                      data-testid={`note-item-${note.id}`}
                      className={`group mb-1 w-full rounded-lg border px-2.5 py-2 text-left transition-colors ${
                        active ? 'border-primary/30 bg-primary/10' : 'hover:bg-muted/50'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="truncate text-sm font-medium">{note.title || '未命名笔记'}</div>
                          <div className="truncate text-[11px] text-muted-foreground">
                            {note.source?.file_name || note.source?.type || 'manual'}
                          </div>
                        </div>
                        <span
                          className="opacity-0 transition-opacity group-hover:opacity-100"
                          onClick={(e) => {
                            e.stopPropagation();
                            onDeleteNote(note.id);
                          }}
                          role="button"
                          title="删除"
                        >
                          <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                        </span>
                      </div>
                      <div className="mt-1 flex items-center justify-between text-[11px] text-muted-foreground">
                        <span>掌握度 {Math.round(note.mastery_score || 0)}</span>
                        <span>{note.links_count || 0} 关联</span>
                      </div>
                    </button>
                  );
                })}
              </div>
            </ScrollArea>
          )}
        </CardContent>
      </Card>
    </CollapsibleColumn>
  );
}
