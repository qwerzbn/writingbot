'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  BookOpen,
  Clock3,
  Loader2,
  MoreHorizontal,
  NotebookPen,
  Pencil,
  Plus,
  Trash2,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  type NotebookListRow,
  createNotebook,
  deleteNotebook,
  listNotebooks,
  updateNotebook,
} from '@/lib/notebook-api';
import { useNotebookWorkspaceUiStore } from '@/lib/stores/notebook-workspace-ui-store';

type NotebookDialogMode = 'create' | 'rename';

function sortNotebooks(rows: NotebookListRow[]): NotebookListRow[] {
  return [...rows].sort((left, right) => {
    const leftTime = new Date(left.updated_at || left.created_at || 0).getTime();
    const rightTime = new Date(right.updated_at || right.created_at || 0).getTime();
    return rightTime - leftTime;
  });
}

function formatUpdatedAt(value?: string | null): string {
  if (!value) return '刚刚更新';
  try {
    return `更新于 ${new Intl.DateTimeFormat('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(value))}`;
  } catch {
    return '刚刚更新';
  }
}

export default function NotebookHubScreen() {
  const router = useRouter();
  const recentNotebookId = useNotebookWorkspaceUiStore((state) => state.recentNotebookId);
  const setRecentNotebookId = useNotebookWorkspaceUiStore((state) => state.setRecentNotebookId);

  const [notebooks, setNotebooks] = useState<NotebookListRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [dialogMode, setDialogMode] = useState<NotebookDialogMode>('create');
  const [dialogNotebookId, setDialogNotebookId] = useState<string | null>(null);
  const [nameInput, setNameInput] = useState('Untitled notebook');
  const [submitting, setSubmitting] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<NotebookListRow | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const run = async () => {
      setLoading(true);
      setError(null);
      try {
        const rows = await listNotebooks();
        if (!cancelled) {
          setNotebooks(sortNotebooks(rows));
        }
      } catch (cause) {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : '加载 notebook 列表失败');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, []);

  const orderedNotebooks = sortNotebooks(notebooks);

  const openCreateDialog = () => {
    setDialogMode('create');
    setDialogNotebookId(null);
    setNameInput('Untitled notebook');
    setDialogOpen(true);
  };

  const openRenameDialog = (notebook: NotebookListRow) => {
    setDialogMode('rename');
    setDialogNotebookId(notebook.id);
    setNameInput(notebook.name);
    setDialogOpen(true);
  };

  const openNotebook = (notebookId: string) => {
    setRecentNotebookId(notebookId);
    router.push(`/notebook/${encodeURIComponent(notebookId)}`);
  };

  const handleSubmitDialog = async () => {
    const trimmedName = nameInput.trim();
    if (!trimmedName) return;

    setSubmitting(true);
    try {
      if (dialogMode === 'create') {
        const created = await createNotebook({ name: trimmedName });
        setNotebooks((prev) => sortNotebooks([created, ...prev]));
      } else if (dialogNotebookId) {
        const updated = await updateNotebook(dialogNotebookId, { name: trimmedName });
        setNotebooks((prev) =>
          sortNotebooks(prev.map((row) => (row.id === dialogNotebookId ? updated : row)))
        );
      }
      setDialogOpen(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '保存 notebook 失败');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteNotebook(deleteTarget.id);
      const next = sortNotebooks(notebooks.filter((row) => row.id !== deleteTarget.id));
      setNotebooks(next);
      if (recentNotebookId === deleteTarget.id) {
        setRecentNotebookId(next[0]?.id ?? null);
      }
      setDeleteTarget(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '删除 notebook 失败');
    } finally {
      setDeleting(false);
    }
  };

  return (
    <>
      <div className="h-full overflow-y-auto bg-slate-50 p-8 dark:bg-slate-950">
        <div className="mx-auto flex max-w-7xl flex-col gap-8">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="text-sm font-medium text-black dark:text-black">Notebook</div>
              <h1 className="mt-2 text-4xl font-semibold tracking-tight text-black ">
                Recent notebooks
              </h1>
            </div>
            <Button
              className="h-12 rounded-full bg-slate-950 px-6 text-sm font-medium text-white hover:bg-slate-800 dark:bg-white dark:text-black dark:hover:bg-slate-200"
              onClick={openCreateDialog}
            >
              <Plus className="h-4 w-4" />
              Create new
            </Button>
          </div>

          {error ? (
            <div className="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700 dark:border-rose-900/50 dark:bg-rose-950/30 dark:text-rose-200">
              {error}
            </div>
          ) : null}

          {loading ? (
            <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
              {Array.from({ length: 4 }).map((_, index) => (
                <div
                  key={index}
                  className="h-64 animate-pulse rounded-[2rem] border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900"
                />
              ))}
            </div>
          ) : (
            <div className="space-y-5">
              {orderedNotebooks.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-slate-200 bg-white px-5 py-4 text-sm text-black dark:border-slate-800 dark:bg-slate-900 dark:text-black">
                  还没有 notebook，先创建你的第一个工作区。
                </div>
              ) : null}

              <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
                <button
                  type="button"
                  onClick={openCreateDialog}
                  className="group flex h-64 flex-col items-center justify-center rounded-[2rem] border border-slate-200 bg-white px-6 text-center shadow-sm transition hover:border-slate-300 hover:shadow-md dark:border-slate-800 dark:bg-slate-900 dark:hover:border-slate-700"
                >
                  <div className="flex h-24 w-24 items-center justify-center rounded-full bg-indigo-50 text-indigo-500 transition group-hover:scale-105 dark:bg-indigo-500/10 dark:text-indigo-300">
                    <Plus className="h-10 w-10" />
                  </div>
                  <div className="mt-6 text-2xl font-medium text-black ">
                    Create new notebook
                  </div>
                </button>

                {orderedNotebooks.map((notebook) => (
                  <div
                    key={notebook.id}
                    className="group relative flex h-64 flex-col rounded-[2rem] border border-slate-200 bg-white p-6 text-left shadow-sm transition hover:border-slate-300 hover:shadow-md dark:border-slate-800 dark:bg-slate-900 dark:hover:border-slate-700"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <button
                        type="button"
                        onClick={() => openNotebook(notebook.id)}
                        className="min-w-0 flex-1 text-left"
                      >
                        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-black dark:bg-slate-800 dark:text-black">
                          <NotebookPen className="h-5 w-5" />
                        </div>
                        <div className="mt-5 truncate text-2xl font-medium text-black ">
                          {notebook.name}
                        </div>
                        <div className="mt-2 flex items-center gap-2 text-sm text-black dark:text-black">
                          <Clock3 className="h-4 w-4" />
                          {formatUpdatedAt(notebook.updated_at || notebook.created_at)}
                        </div>
                      </button>

                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <button
                            type="button"
                            className="flex h-10 w-10 items-center justify-center rounded-full text-black transition hover:bg-slate-100 hover:text-black dark:hover:bg-slate-800 dark:hover:text-black"
                            onClick={(event) => event.stopPropagation()}
                          >
                            <MoreHorizontal className="h-5 w-5" />
                          </button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent
                          align="end"
                          className="w-40 rounded-xl border-slate-200 bg-white p-1 shadow-lg dark:border-slate-800 dark:bg-slate-900"
                        >
                          <DropdownMenuItem
                            onClick={() => openRenameDialog(notebook)}
                            className="rounded-lg text-sm"
                          >
                            <Pencil className="h-4 w-4" />
                            重命名
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            variant="destructive"
                            onClick={() => setDeleteTarget(notebook)}
                            className="rounded-lg text-sm"
                          >
                            <Trash2 className="h-4 w-4" />
                            删除
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>

                    <div className="mt-auto flex items-center gap-2 text-sm text-black dark:text-black">
                      <div className="inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1.5 dark:bg-slate-800">
                        <BookOpen className="h-4 w-4" />
                        {notebook.source_count} 来源
                      </div>
                      <div className="inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1.5 dark:bg-slate-800">
                        <NotebookPen className="h-4 w-4" />
                        {notebook.note_count} 笔记
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-md rounded-3xl border-slate-200 bg-white p-0 shadow-xl dark:border-slate-800 dark:bg-slate-900">
          <DialogHeader className="border-b border-slate-200 px-6 py-5 dark:border-slate-800">
            <DialogTitle className="text-lg font-semibold text-black ">
              {dialogMode === 'create' ? 'Create new notebook' : '重命名 notebook'}
            </DialogTitle>
            <DialogDescription className="text-sm text-black dark:text-black">
              {dialogMode === 'create'
                ? '输入一个 notebook 名称，创建后会出现在列表中。'
                : '更新当前 notebook 的显示名称。'}
            </DialogDescription>
          </DialogHeader>
          <div className="px-6 py-6">
            <label className="mb-2 block text-sm font-medium text-black dark:text-black">
              Notebook 名称
            </label>
            <input
              value={nameInput}
              onChange={(event) => setNameInput(event.target.value)}
              placeholder="Untitled notebook"
              className="h-12 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 text-sm text-black outline-none transition focus:border-slate-300 dark:border-slate-700 dark:bg-slate-800  dark:focus:border-slate-600"
            />
          </div>
          <DialogFooter className="border-t border-slate-200 px-6 py-5 dark:border-slate-800">
            <Button
              variant="outline"
              className="rounded-full border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900"
              onClick={() => setDialogOpen(false)}
            >
              取消
            </Button>
            <Button
              className="rounded-full bg-slate-950 text-black hover:bg-slate-800 dark:bg-white dark:text-black dark:hover:bg-slate-200"
              onClick={() => void handleSubmitDialog()}
              disabled={submitting || !nameInput.trim()}
            >
              {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              {dialogMode === 'create' ? '创建' : '保存'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(deleteTarget)} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <DialogContent className="max-w-md rounded-3xl border-slate-200 bg-white p-0 shadow-xl dark:border-slate-800 dark:bg-slate-900">
          <DialogHeader className="border-b border-slate-200 px-6 py-5 dark:border-slate-800">
            <DialogTitle className="text-lg font-semibold text-black ">
              删除 notebook
            </DialogTitle>
            <DialogDescription className="text-sm text-black dark:text-black">
              {deleteTarget ? `确认删除“${deleteTarget.name}”吗？此操作无法撤销。` : '确认删除当前 notebook 吗？'}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="border-t border-slate-200 px-6 py-5 dark:border-slate-800">
            <Button
              variant="outline"
              className="rounded-full border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900"
              onClick={() => setDeleteTarget(null)}
            >
              取消
            </Button>
            <Button
              variant="destructive"
              className="rounded-full"
              onClick={() => void handleDelete()}
              disabled={deleting}
            >
              {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
              删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
