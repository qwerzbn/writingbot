import { create } from 'zustand';

import type { NotebookNoteDetail, WorkspaceNoteSummary } from '@/lib/notebook-api';

interface NotebookNotesState {
  notesByNotebook: Record<string, WorkspaceNoteSummary[]>;
  activeNoteIdByNotebook: Record<string, string | null>;
  noteDetailById: Record<string, NotebookNoteDetail>;
  notesLoadingByNotebook: Record<string, boolean>;
  noteLoadingById: Record<string, boolean>;
  seedWorkspaceNotes: (
    notebookId: string,
    notes: WorkspaceNoteSummary[],
    activeNoteId: string | null
  ) => void;
  setNotesLoading: (notebookId: string, loading: boolean) => void;
  setNoteLoading: (noteId: string, loading: boolean) => void;
  setActiveNote: (notebookId: string, noteId: string | null) => void;
  setNoteDetail: (detail: NotebookNoteDetail) => void;
  upsertNoteSummary: (notebookId: string, detail: NotebookNoteDetail) => void;
  removeNote: (notebookId: string, noteId: string) => void;
  clearNotebook: (notebookId: string) => void;
}

function sourceLabel(detail: NotebookNoteDetail | WorkspaceNoteSummary): string {
  const source = detail.source || {};
  if (source.type === 'knowledge_base') {
    return `${source.file_name || source.file_id || '知识库文件'}${
      source.page !== undefined && source.page !== null ? ` · p.${source.page}` : ''
    }`;
  }
  if (source.type === 'research') return '研究结果';
  if (source.type === 'co_writer') return '协同写作';
  return '手动笔记';
}

export const useNotebookNotesStore = create<NotebookNotesState>((set) => ({
  notesByNotebook: {},
  activeNoteIdByNotebook: {},
  noteDetailById: {},
  notesLoadingByNotebook: {},
  noteLoadingById: {},
  seedWorkspaceNotes: (notebookId, notes, activeNoteId) =>
    set((state) => {
      const existingActive = state.activeNoteIdByNotebook[notebookId];
      const availableIds = new Set(notes.map((note) => note.id));
      const nextActive =
        existingActive && availableIds.has(existingActive)
          ? existingActive
          : activeNoteId && availableIds.has(activeNoteId)
            ? activeNoteId
            : notes[0]?.id || null;
      return {
        notesByNotebook: { ...state.notesByNotebook, [notebookId]: notes },
        activeNoteIdByNotebook: {
          ...state.activeNoteIdByNotebook,
          [notebookId]: nextActive,
        },
      };
    }),
  setNotesLoading: (notebookId, loading) =>
    set((state) => ({
      notesLoadingByNotebook: { ...state.notesLoadingByNotebook, [notebookId]: loading },
    })),
  setNoteLoading: (noteId, loading) =>
    set((state) => ({
      noteLoadingById: { ...state.noteLoadingById, [noteId]: loading },
    })),
  setActiveNote: (notebookId, noteId) =>
    set((state) => ({
      activeNoteIdByNotebook: { ...state.activeNoteIdByNotebook, [notebookId]: noteId },
    })),
  setNoteDetail: (detail) =>
    set((state) => ({
      noteDetailById: { ...state.noteDetailById, [detail.id]: detail },
    })),
  upsertNoteSummary: (notebookId, detail) =>
    set((state) => {
      const existing = state.notesByNotebook[notebookId] ?? [];
      const nextSummary: WorkspaceNoteSummary = {
        id: detail.id,
        notebook_id: detail.notebook_id,
        title: detail.title,
        tags: detail.tags,
        source: detail.source,
        content_preview: detail.content.slice(0, 140),
        updated_at: detail.updated_at,
        created_at: detail.created_at,
        source_label: sourceLabel(detail),
      };
      const matchIndex = existing.findIndex((note) => note.id === detail.id);
      const nextNotes =
        matchIndex >= 0
          ? existing.map((note, index) => (index === matchIndex ? { ...note, ...nextSummary } : note))
          : [nextSummary, ...existing];
      return {
        notesByNotebook: {
          ...state.notesByNotebook,
          [notebookId]: nextNotes,
        },
      };
    }),
  removeNote: (notebookId, noteId) =>
    set((state) => {
      const filtered = (state.notesByNotebook[notebookId] ?? []).filter((note) => note.id !== noteId);
      const nextActive =
        state.activeNoteIdByNotebook[notebookId] === noteId
          ? filtered[0]?.id || null
          : state.activeNoteIdByNotebook[notebookId] ?? null;
      const nextDetailById = { ...state.noteDetailById };
      delete nextDetailById[noteId];
      return {
        notesByNotebook: { ...state.notesByNotebook, [notebookId]: filtered },
        activeNoteIdByNotebook: { ...state.activeNoteIdByNotebook, [notebookId]: nextActive },
        noteDetailById: nextDetailById,
      };
    }),
  clearNotebook: (notebookId) =>
    set((state) => ({
      notesByNotebook: { ...state.notesByNotebook, [notebookId]: [] },
      activeNoteIdByNotebook: { ...state.activeNoteIdByNotebook, [notebookId]: null },
    })),
}));
