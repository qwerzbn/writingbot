'use client';

import { Activity, BookOpen, Database, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface ActiveNotebook {
  id: string;
  name: string;
  description?: string;
  note_count?: number;
  record_count?: number;
  auto_import_enabled?: boolean;
}

interface NotebookHeaderProps {
  notebook: ActiveNotebook | null;
  disabled?: boolean;
  onToggleAutoImport: (enabled: boolean) => void;
  onMigrateRecords: () => void;
}

export default function NotebookHeader({
  notebook,
  disabled,
  onToggleAutoImport,
  onMigrateRecords,
}: NotebookHeaderProps) {
  return (
    <div className="rounded-xl border bg-card px-4 py-3" data-testid="notebook-header">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <BookOpen className="h-4 w-4 text-primary" />
            <h1 className="truncate text-base font-semibold">
              {notebook?.name || '未选择笔记本'}
            </h1>
          </div>
          <p className="mt-1 truncate text-xs text-muted-foreground">
            {notebook?.description || '三栏工作台：资料、笔记与编辑'}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <label className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs">
            <input
              type="checkbox"
              disabled={disabled}
              checked={Boolean(notebook?.auto_import_enabled)}
              onChange={(e) => onToggleAutoImport(e.target.checked)}
            />
            <span>自动候选卡片</span>
          </label>
          <Button
            variant="outline"
            size="sm"
            disabled={disabled}
            onClick={onMigrateRecords}
            className="h-8"
            title="首次升级后可执行 records 迁移"
            data-testid="notebook-migrate-records"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            迁移 records
          </Button>
        </div>
      </div>

      {notebook && (
        <div className="mt-3 grid grid-cols-3 gap-2 text-xs text-muted-foreground">
          <div className="rounded-md border bg-muted/30 px-2 py-1.5">
            <div className="flex items-center gap-1">
              <BookOpen className="h-3.5 w-3.5" />
              笔记
            </div>
            <div className="mt-0.5 text-foreground">{notebook.note_count || 0}</div>
          </div>
          <div className="rounded-md border bg-muted/30 px-2 py-1.5">
            <div className="flex items-center gap-1">
              <Database className="h-3.5 w-3.5" />
              records
            </div>
            <div className="mt-0.5 text-foreground">{notebook.record_count || 0}</div>
          </div>
          <div className="rounded-md border bg-muted/30 px-2 py-1.5">
            <div className="flex items-center gap-1">
              <Activity className="h-3.5 w-3.5" />
              状态
            </div>
            <div className="mt-0.5 text-foreground">{disabled ? '未就绪' : '可编辑'}</div>
          </div>
        </div>
      )}
    </div>
  );
}
