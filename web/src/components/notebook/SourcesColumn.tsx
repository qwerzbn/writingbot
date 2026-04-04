'use client';

import { useMemo, useState } from 'react';
import { Database, Loader2, Plus, Sparkles, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { CollapsibleColumn, createCollapseButton } from '@/components/notebook/CollapsibleColumn';
import { useNotebookColumnsStore } from '@/lib/stores/notebook-columns-store';

interface NotebookRow {
  id: string;
  name: string;
  description?: string;
  note_count?: number;
  record_count?: number;
}

interface ImportJob {
  id: string;
  status: 'pending' | 'running' | 'done' | 'partial_failed';
  progress: number;
  processed: number;
  total: number;
  note_ids?: string[];
}

interface SourcesColumnProps {
  notebooks: NotebookRow[];
  selectedNotebookId: string | null;
  loading: boolean;
  importKbOptions: Array<{ id: string; name: string }>;
  selectedImportKbId: string;
  importing: boolean;
  importJob: ImportJob | null;
  disabled?: boolean;
  onSelectNotebook: (id: string) => void;
  onDeleteNotebook: (id: string) => void;
  onCreateNotebook: (name: string, desc: string) => void;
  onImportKbChange: (kbId: string) => void;
  onImportFromKb: () => void;
  onOpenImportedFirstNote: () => void;
}

export default function SourcesColumn({
  notebooks,
  selectedNotebookId,
  loading,
  importKbOptions,
  selectedImportKbId,
  importing,
  importJob,
  disabled,
  onSelectNotebook,
  onDeleteNotebook,
  onCreateNotebook,
  onImportKbChange,
  onImportFromKb,
  onOpenImportedFirstNote,
}: SourcesColumnProps) {
  const { sourcesCollapsed, toggleSources } = useNotebookColumnsStore();
  const collapseButton = useMemo(() => createCollapseButton(toggleSources, '资料'), [toggleSources]);

  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');

  const submitCreate = () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    onCreateNotebook(trimmed, desc.trim());
    setShowCreate(false);
    setName('');
    setDesc('');
  };

  return (
    <CollapsibleColumn
      isCollapsed={sourcesCollapsed}
      onToggle={toggleSources}
      collapsedIcon={Database}
      collapsedLabel="资料"
    >
      <Card className="flex h-full flex-col gap-0 py-0" data-testid="notebook-sources-column">
        <CardHeader className="border-b py-3">
          <div className="flex items-center justify-between gap-2">
            <CardTitle className="text-sm">资料与笔记本</CardTitle>
            <div className="flex items-center gap-1">
              <Button
                size="sm"
                variant="outline"
                onClick={() => setShowCreate((v) => !v)}
                className="h-8"
                data-testid="notebook-create-notebook-toggle"
              >
                <Plus className="h-3.5 w-3.5" />
                新建
              </Button>
              {collapseButton}
            </div>
          </div>
          {showCreate && (
            <div className="mt-2 space-y-2">
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="笔记本名称"
                className="h-9 w-full rounded-md border bg-background px-2.5 text-sm"
                data-testid="notebook-create-name"
              />
              <input
                value={desc}
                onChange={(e) => setDesc(e.target.value)}
                placeholder="描述（可选）"
                className="h-9 w-full rounded-md border bg-background px-2.5 text-sm"
                data-testid="notebook-create-desc"
              />
              <div className="flex items-center gap-2">
                <Button size="sm" onClick={submitCreate} data-testid="notebook-create-submit">创建</Button>
                <Button size="sm" variant="outline" onClick={() => setShowCreate(false)}>取消</Button>
              </div>
            </div>
          )}

          <div className="mt-3 grid grid-cols-[1fr_auto] gap-2">
            <select
              value={selectedImportKbId}
              onChange={(e) => onImportKbChange(e.target.value)}
              className="h-9 rounded-md border bg-background px-2.5 text-xs"
              data-testid="notebook-import-kb-select"
            >
              <option value="">选择知识库</option>
              {importKbOptions.map((kb) => (
                <option key={kb.id} value={kb.id}>
                  {kb.name}
                </option>
              ))}
            </select>
            <Button
              size="sm"
              disabled={disabled || !selectedImportKbId || importing}
              onClick={onImportFromKb}
              className="h-9"
              data-testid="notebook-import-kb"
            >
              {importing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
              生成
            </Button>
          </div>

          {importJob && (
            <div className="mt-2 rounded-md border bg-muted/40 px-2.5 py-2 text-[11px]" data-testid="notebook-import-job">
              <div className="flex items-center justify-between">
                <span>任务：{importJob.status}</span>
                <span>{Math.round((importJob.progress || 0) * 100)}%</span>
              </div>
              <div className="mt-1 h-1.5 overflow-hidden rounded bg-muted">
                <div className="h-full bg-primary transition-all" style={{ width: `${Math.round((importJob.progress || 0) * 100)}%` }} />
              </div>
              <div className="mt-1">
                {importJob.processed || 0}/{importJob.total || 0} 文件
                {(importJob.note_ids || []).length > 0 && (
                  <button className="ml-2 underline" onClick={onOpenImportedFirstNote} data-testid="notebook-open-first-imported-note">
                    打开首个卡片
                  </button>
                )}
              </div>
            </div>
          )}
        </CardHeader>

        <CardContent className="min-h-0 flex-1 px-0">
          {loading ? (
            <div className="flex items-center gap-2 px-4 py-3 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              加载笔记本
            </div>
          ) : notebooks.length === 0 ? (
            <div className="px-4 py-6 text-sm text-muted-foreground">暂无笔记本</div>
          ) : (
            <ScrollArea className="h-full">
              <div className="px-2 py-2">
                {notebooks.map((nb) => {
                  const active = selectedNotebookId === nb.id;
                  return (
                    <button
                      key={nb.id}
                      onClick={() => onSelectNotebook(nb.id)}
                      data-testid={`notebook-item-${nb.id}`}
                      className={`group mb-1 w-full rounded-lg border px-2.5 py-2 text-left transition-colors ${
                        active ? 'border-primary/30 bg-primary/10' : 'hover:bg-muted/50'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="truncate text-sm font-medium">{nb.name}</div>
                          <div className="text-[11px] text-muted-foreground">
                            {nb.note_count || 0} 笔记 · {nb.record_count || 0} records
                          </div>
                        </div>
                        <span
                          className="opacity-0 transition-opacity group-hover:opacity-100"
                          onClick={(e) => {
                            e.stopPropagation();
                            onDeleteNotebook(nb.id);
                          }}
                          role="button"
                          title="删除"
                        >
                          <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                        </span>
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
