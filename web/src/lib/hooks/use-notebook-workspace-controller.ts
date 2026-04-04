'use client';

import {
  startTransition,
  useCallback,
  useEffect,
  useEffectEvent,
  useRef,
  useState,
} from 'react';
import { useRouter } from 'next/navigation';

import { useAppContext } from '@/context/AppContext';
import {
  type GraphViewPayload,
  type NotebookApiError,
  type NotebookEvent,
  type NotebookJob,
  type NotebookNoteDetail,
  type NotebookNoteMeta,
  type RelatedNote,
  createNote,
  createNotebook,
  deleteNote,
  deleteNotebook,
  getGraphView,
  getNoteDetail,
  getNoteMeta,
  getNotebookWorkspace,
  getRelatedNotes,
  migrateNotebookRecords,
  rerunExtraction,
  startNotebookImport,
  updateNote,
  updateNotebook,
} from '@/lib/notebook-api';
import { useNotebookContextStore } from '@/lib/stores/notebook-context-store';
import { useNotebookJobsStore } from '@/lib/stores/notebook-jobs-store';
import { useNotebookNotesStore } from '@/lib/stores/notebook-notes-store';
import { useNotebookWorkspaceUiStore } from '@/lib/stores/notebook-workspace-ui-store';

const EMPTY_FILTERS = { search: '', tag: '' };
const EMPTY_NOTES: ReturnType<typeof useNotebookNotesStore.getState>['notesByNotebook'][string] = [];
const EMPTY_JOBS: NotebookJob[] = [];

function messageFromError(error: unknown, fallback: string): string {
  if (error && typeof error === 'object' && 'message' in error && typeof error.message === 'string') {
    return error.message;
  }
  return fallback;
}

export function useNotebookWorkspaceController(notebookId: string) {
  const router = useRouter();
  const { selectedKbId } = useAppContext();

  const filters = useNotebookWorkspaceUiStore(
    (state) => state.filtersByNotebook[notebookId] ?? EMPTY_FILTERS
  );
  const activeContextTab = useNotebookWorkspaceUiStore(
    (state) => state.contextTabByNotebook[notebookId] ?? 'insights'
  );
  const activeNotebook = useNotebookWorkspaceUiStore((state) => state.activeNotebook);
  const notebooks = useNotebookWorkspaceUiStore((state) => state.notebooks);
  const recentNotebookId = useNotebookWorkspaceUiStore((state) => state.recentNotebookId);
  const setWorkspaceSnapshot = useNotebookWorkspaceUiStore((state) => state.setWorkspaceSnapshot);
  const setRecentNotebookId = useNotebookWorkspaceUiStore((state) => state.setRecentNotebookId);

  const notes = useNotebookNotesStore((state) => state.notesByNotebook[notebookId] ?? EMPTY_NOTES);
  const activeNoteId = useNotebookNotesStore((state) => state.activeNoteIdByNotebook[notebookId] ?? null);
  const activeNote = useNotebookNotesStore((state) =>
    activeNoteId ? state.noteDetailById[activeNoteId] ?? null : null
  );
  const activeJobs = useNotebookJobsStore((state) => state.jobsByNotebook[notebookId] ?? EMPTY_JOBS);
  const graph = useNotebookContextStore((state) => state.graphByNotebook[notebookId]);
  const graphDirty = useNotebookContextStore((state) => state.graphDirtyByNotebook[notebookId] ?? true);

  const seedWorkspaceNotes = useNotebookNotesStore((state) => state.seedWorkspaceNotes);
  const setActiveNote = useNotebookNotesStore((state) => state.setActiveNote);
  const setNoteDetail = useNotebookNotesStore((state) => state.setNoteDetail);
  const setNotesLoading = useNotebookNotesStore((state) => state.setNotesLoading);
  const setNoteLoading = useNotebookNotesStore((state) => state.setNoteLoading);
  const upsertNoteSummary = useNotebookNotesStore((state) => state.upsertNoteSummary);
  const removeNoteFromStore = useNotebookNotesStore((state) => state.removeNote);

  const seedInsights = useNotebookContextStore((state) => state.seedInsights);
  const setGraph = useNotebookContextStore((state) => state.setGraph);
  const setGraphLoading = useNotebookContextStore((state) => state.setGraphLoading);
  const markContextDirty = useNotebookContextStore((state) => state.markContextDirty);
  const setRelated = useNotebookContextStore((state) => state.setRelated);
  const setRelatedLoading = useNotebookContextStore((state) => state.setRelatedLoading);
  const setMeta = useNotebookContextStore((state) => state.setMeta);
  const setMetaLoading = useNotebookContextStore((state) => state.setMetaLoading);

  const seedJobs = useNotebookJobsStore((state) => state.seedJobs);
  const upsertJob = useNotebookJobsStore((state) => state.upsertJob);
  const applyJobEvent = useNotebookJobsStore((state) => state.applyEvent);
  const setLatestCompletedJob = useNotebookJobsStore((state) => state.setLatestCompletedJob);
  const setStreamStatus = useNotebookJobsStore((state) => state.setStreamStatus);

  const [workspaceLoading, setWorkspaceLoading] = useState(true);
  const [workspaceRefreshing, setWorkspaceRefreshing] = useState(false);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const [importPending, setImportPending] = useState(false);
  const [extractingNoteId, setExtractingNoteId] = useState<string | null>(null);
  const [migrating, setMigrating] = useState(false);

  const didBootstrapRef = useRef(false);

  const loadNoteDetail = useCallback(
    async (noteId: string, options?: { force?: boolean }) => {
      const currentNotesState = useNotebookNotesStore.getState();
      const currentActiveId = currentNotesState.activeNoteIdByNotebook[notebookId] ?? null;
      const currentDetail = currentNotesState.noteDetailById[noteId] ?? null;
      if (!options?.force && currentActiveId === noteId && currentDetail) {
        return currentDetail;
      }
      setActiveNote(notebookId, noteId);
      setNoteLoading(noteId, true);
      try {
        const detail = await getNoteDetail(notebookId, noteId);
        startTransition(() => {
          setNoteDetail(detail);
          upsertNoteSummary(notebookId, detail);
        });
        return detail;
      } catch (error) {
        setWorkspaceError(messageFromError(error, '加载笔记详情失败'));
        return null;
      } finally {
        setNoteLoading(noteId, false);
      }
    },
    [notebookId, setActiveNote, setNoteDetail, setNoteLoading, upsertNoteSummary]
  );

  const refreshWorkspace = useCallback(
    async (options?: { silent?: boolean; activeNoteOverride?: string | null }) => {
      const currentNotesState = useNotebookNotesStore.getState();
      const currentActiveNoteId = currentNotesState.activeNoteIdByNotebook[notebookId] ?? null;
      if (options?.silent) {
        setWorkspaceRefreshing(true);
      } else {
        setWorkspaceLoading(true);
      }
      setNotesLoading(notebookId, true);
      try {
        const data = await getNotebookWorkspace(notebookId, {
          activeNoteId: options?.activeNoteOverride ?? currentActiveNoteId,
          search: filters.search,
          tag: filters.tag,
        });
        startTransition(() => {
          setWorkspaceSnapshot(notebookId, data);
          seedWorkspaceNotes(
            notebookId,
            data.notes,
            (options?.activeNoteOverride ?? currentActiveNoteId) || data.view_state_defaults.active_note_id
          );
          seedInsights(notebookId, data.insights_summary);
          seedJobs(notebookId, data.active_jobs);
          markContextDirty(notebookId, false);
        });
        setRecentNotebookId(notebookId);
        const nextActiveId =
          options?.activeNoteOverride ??
          currentActiveNoteId ??
          data.view_state_defaults.active_note_id ??
          data.active_note_summary?.id ??
          null;
        if (nextActiveId) {
          void loadNoteDetail(nextActiveId);
        }
        setWorkspaceError(null);
        return data;
      } catch (error) {
        setWorkspaceError(messageFromError(error, '加载工作台失败'));
        return null;
      } finally {
        setNotesLoading(notebookId, false);
        setWorkspaceLoading(false);
        setWorkspaceRefreshing(false);
      }
    },
    [
      filters.search,
      filters.tag,
      loadNoteDetail,
      markContextDirty,
      notebookId,
      seedInsights,
      seedJobs,
      seedWorkspaceNotes,
      setNotesLoading,
      setRecentNotebookId,
      setWorkspaceSnapshot,
    ]
  );

  const ensureGraphLoaded = useCallback(
    async (force = false): Promise<GraphViewPayload | null> => {
      if (!force && graph && !graphDirty) {
        return graph;
      }
      setGraphLoading(notebookId, true);
      try {
        const payload = await getGraphView(notebookId, force || graphDirty);
        startTransition(() => {
          setGraph(notebookId, payload);
        });
        return payload;
      } catch (error) {
        setWorkspaceError(messageFromError(error, '加载图谱失败'));
        return null;
      } finally {
        setGraphLoading(notebookId, false);
      }
    },
    [graph, graphDirty, notebookId, setGraph, setGraphLoading]
  );

  const ensureRelatedLoaded = useCallback(
    async (noteId: string, force = false): Promise<RelatedNote[]> => {
      const cached = useNotebookContextStore.getState().relatedByNote[noteId];
      if (!force && cached) return cached;
      setRelatedLoading(noteId, true);
      try {
        const rows = await getRelatedNotes(notebookId, noteId);
        startTransition(() => setRelated(noteId, rows));
        return rows;
      } finally {
        setRelatedLoading(noteId, false);
      }
    },
    [notebookId, setRelated, setRelatedLoading]
  );

  const ensureMetaLoaded = useCallback(
    async (noteId: string, force = false): Promise<NotebookNoteMeta | null> => {
      const cached = useNotebookContextStore.getState().metaByNote[noteId];
      if (!force && cached) return cached;
      setMetaLoading(noteId, true);
      try {
        const meta = await getNoteMeta(notebookId, noteId);
        startTransition(() => setMeta(noteId, meta));
        return meta;
      } catch {
        return null;
      } finally {
        setMetaLoading(noteId, false);
      }
    },
    [notebookId, setMeta, setMetaLoading]
  );

  const handleNotebookEvent = useEffectEvent((event: NotebookEvent) => {
    applyJobEvent(notebookId, event);
    if (event.type === 'context_invalidated') {
      markContextDirty(notebookId, true);
      void refreshWorkspace({ silent: true });
      if (activeContextTab === 'graph') {
        void ensureGraphLoaded(true);
      }
      if (activeNoteId && event.affected_note_ids?.includes(activeNoteId)) {
        void loadNoteDetail(activeNoteId, { force: true });
      }
    }
    if (event.type === 'done' && activeContextTab === 'graph') {
      void ensureGraphLoaded(true);
    }
  });

  useEffect(() => {
    didBootstrapRef.current = false;
    void refreshWorkspace();
  }, [notebookId, refreshWorkspace]);

  useEffect(() => {
    if (!didBootstrapRef.current) {
      didBootstrapRef.current = true;
      return;
    }
    const timer = window.setTimeout(() => {
      void refreshWorkspace({ silent: true });
    }, 280);
    return () => window.clearTimeout(timer);
  }, [filters.search, filters.tag, notebookId, refreshWorkspace]);

  useEffect(() => {
    if (!activeNoteId) return;
    if (activeContextTab === 'graph') {
      void ensureGraphLoaded();
    }
    if (activeContextTab === 'related') {
      void ensureRelatedLoaded(activeNoteId);
    }
    if (activeContextTab === 'evidence') {
      void ensureMetaLoaded(activeNoteId);
    }
  }, [activeContextTab, activeNoteId, ensureGraphLoaded, ensureMetaLoaded, ensureRelatedLoaded]);

  useEffect(() => {
    const shouldStream = activeJobs.some((job) => job.status === 'pending' || job.status === 'running');
    if (!shouldStream) {
      setStreamStatus(notebookId, 'idle');
      return;
    }

    setStreamStatus(notebookId, 'connecting');
    const source = new EventSource(`/api/notebooks/${notebookId}/events`);

    source.onopen = () => setStreamStatus(notebookId, 'open');
    source.onmessage = (message) => {
      try {
        const payload = JSON.parse(message.data) as NotebookEvent;
        handleNotebookEvent(payload);
      } catch {
        // Ignore malformed keep-alives.
      }
    };
    source.onerror = () => {
      source.close();
      setStreamStatus(notebookId, 'error');
      void (async () => {
        const previousJobs = useNotebookJobsStore.getState().jobsByNotebook[notebookId] ?? EMPTY_JOBS;
        if (!previousJobs.length) return;

        const previousNoteIds = new Set(
          (useNotebookNotesStore.getState().notesByNotebook[notebookId] ?? EMPTY_NOTES).map(
            (note) => note.id
          )
        );
        const data = await refreshWorkspace({ silent: true });
        if (data && data.active_jobs.length === 0) {
          const recoveredJob = previousJobs[0];
          const recoveredNoteIds = data.notes
            .map((note) => note.id)
            .filter((noteId) => !previousNoteIds.has(noteId));
          setLatestCompletedJob(notebookId, {
            ...recoveredJob,
            status: 'done',
            progress: 1,
            updated_at: data.generated_at,
            message: recoveredJob.message || 'Job finished',
            note_ids: recoveredNoteIds.length ? recoveredNoteIds : recoveredJob.note_ids,
          });
          setStreamStatus(notebookId, 'idle');
        }
      })();
    };

    return () => source.close();
  }, [
    activeJobs,
    notebookId,
    refreshWorkspace,
    setLatestCompletedJob,
    setStreamStatus,
  ]);

  const saveNoteDraft = useCallback(
    async (
      noteId: string,
      payload: { title?: string; content?: string; tags?: string[]; expected_updated_at: string }
    ) => {
      try {
        const updated = await updateNote(notebookId, noteId, payload);
        startTransition(() => {
          setNoteDetail(updated);
          upsertNoteSummary(notebookId, updated);
          markContextDirty(notebookId, true);
        });
        return { updated };
      } catch (error) {
        const apiError = error as NotebookApiError;
        if (apiError?.status === 409) {
          const latest = (apiError.payload as { detail?: { latest?: NotebookNoteDetail } })?.detail?.latest;
          if (latest) {
            startTransition(() => {
              setNoteDetail(latest);
              upsertNoteSummary(notebookId, latest);
            });
            return { conflict: '检测到并发修改，已加载最新版本。', latest };
          }
          return { conflict: '保存冲突，请刷新后重试。' };
        }
        return { error: messageFromError(error, '保存失败，请稍后重试。') };
      }
    },
    [markContextDirty, notebookId, setNoteDetail, upsertNoteSummary]
  );

  const handleCreateNotebook = useCallback(
    async (name: string, description: string) => {
      const notebook = await createNotebook({
        name: name.trim(),
        description: description.trim(),
        default_kb_id: selectedKbId,
        auto_import_enabled: false,
      });
      setRecentNotebookId(notebook.id);
      router.push(`/notebook/${encodeURIComponent(notebook.id)}`);
    },
    [router, selectedKbId, setRecentNotebookId]
  );

  const handleDeleteNotebook = useCallback(
    async (targetNotebookId: string) => {
      await deleteNotebook(targetNotebookId);
      if (targetNotebookId === notebookId) {
        const nextId =
          notebooks.find((row) => row.id !== targetNotebookId)?.id || recentNotebookId;
        if (nextId && nextId !== targetNotebookId) {
          router.push(`/notebook/${encodeURIComponent(nextId)}`);
          return;
        }
        router.push('/notebook');
      } else {
        void refreshWorkspace({ silent: true });
      }
    },
    [notebookId, notebooks, recentNotebookId, refreshWorkspace, router]
  );

  const handleCreateNote = useCallback(async () => {
    const detail = await createNote(notebookId, {
      title: '新笔记',
      content: '',
      tags: [],
      source: { type: 'manual' },
    });
    startTransition(() => {
      setActiveNote(notebookId, detail.id);
      setNoteDetail(detail);
      upsertNoteSummary(notebookId, detail);
      markContextDirty(notebookId, true);
    });
    void refreshWorkspace({ silent: true, activeNoteOverride: detail.id });
  }, [markContextDirty, notebookId, refreshWorkspace, setActiveNote, setNoteDetail, upsertNoteSummary]);

  const handleDeleteNote = useCallback(
    async (noteId: string) => {
      await deleteNote(notebookId, noteId);
      startTransition(() => removeNoteFromStore(notebookId, noteId));
      markContextDirty(notebookId, true);
      void refreshWorkspace({ silent: true });
    },
    [markContextDirty, notebookId, refreshWorkspace, removeNoteFromStore]
  );

  const handleStartImport = useCallback(
    async (kbId: string) => {
      setImportPending(true);
      try {
        const job = await startNotebookImport(notebookId, kbId);
        const seededJob: NotebookJob = {
          id: job.id,
          job_type: 'import_kb',
          status: job.status,
          progress: job.progress,
          processed: job.processed,
          total: job.total,
          note_ids: job.note_ids ?? [],
          message: `${job.processed}/${job.total} files`,
        };
        startTransition(() => upsertJob(notebookId, seededJob));
      } finally {
        setImportPending(false);
      }
    },
    [notebookId, upsertJob]
  );

  const handleRerunExtraction = useCallback(async () => {
    if (!activeNoteId) return;
    setExtractingNoteId(activeNoteId);
    try {
      const result = await rerunExtraction(notebookId, activeNoteId);
      if (result.note) {
        startTransition(() => {
          setNoteDetail(result.note);
          upsertNoteSummary(notebookId, result.note);
          markContextDirty(notebookId, true);
        });
        const resultMeta = result.meta;
        if (resultMeta) {
          startTransition(() => setMeta(activeNoteId, resultMeta));
        }
      }
      void refreshWorkspace({ silent: true, activeNoteOverride: activeNoteId });
    } finally {
      setExtractingNoteId(null);
    }
  }, [activeNoteId, markContextDirty, notebookId, refreshWorkspace, setMeta, setNoteDetail, upsertNoteSummary]);

  const handleMigrateRecords = useCallback(async () => {
    setMigrating(true);
    try {
      await migrateNotebookRecords(notebookId);
      markContextDirty(notebookId, true);
      await refreshWorkspace({ silent: true });
    } finally {
      setMigrating(false);
    }
  }, [markContextDirty, notebookId, refreshWorkspace]);

  const handleNotebookSettings = useCallback(
    async (payload: { default_kb_id?: string | null; auto_import_enabled?: boolean }) => {
      await updateNotebook(notebookId, payload);
      await refreshWorkspace({ silent: true });
    },
    [notebookId, refreshWorkspace]
  );

  return {
    workspaceLoading,
    workspaceRefreshing,
    workspaceError,
    importPending,
    extractingNoteId,
    migrating,
    activeNotebook,
    notes,
    activeNoteId,
    activeNote,
    activeJobs,
    graph,
    refreshWorkspace,
    loadNoteDetail,
    ensureGraphLoaded,
    ensureRelatedLoaded,
    ensureMetaLoaded,
    saveNoteDraft,
    createNotebook: handleCreateNotebook,
    deleteNotebook: handleDeleteNotebook,
    createNote: handleCreateNote,
    deleteNote: handleDeleteNote,
    startImport: handleStartImport,
    rerunCurrentNoteExtraction: handleRerunExtraction,
    migrateRecords: handleMigrateRecords,
    updateNotebookSettings: handleNotebookSettings,
  };
}
