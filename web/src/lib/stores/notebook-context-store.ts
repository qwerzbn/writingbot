import { create } from 'zustand';

import type {
  GraphViewPayload,
  NotebookNoteMeta,
  NotebookWorkspaceData,
  RelatedNote,
} from '@/lib/notebook-api';

interface NotebookContextState {
  insightsByNotebook: Record<string, NotebookWorkspaceData['insights_summary']>;
  graphByNotebook: Record<string, GraphViewPayload>;
  graphDirtyByNotebook: Record<string, boolean>;
  graphLoadingByNotebook: Record<string, boolean>;
  relatedByNote: Record<string, RelatedNote[]>;
  relatedLoadingByNote: Record<string, boolean>;
  metaByNote: Record<string, NotebookNoteMeta>;
  metaLoadingByNote: Record<string, boolean>;
  seedInsights: (notebookId: string, insights: NotebookWorkspaceData['insights_summary']) => void;
  setGraph: (notebookId: string, graph: GraphViewPayload) => void;
  setGraphLoading: (notebookId: string, loading: boolean) => void;
  markContextDirty: (notebookId: string, dirty: boolean) => void;
  setRelated: (noteId: string, related: RelatedNote[]) => void;
  setRelatedLoading: (noteId: string, loading: boolean) => void;
  setMeta: (noteId: string, meta: NotebookNoteMeta) => void;
  setMetaLoading: (noteId: string, loading: boolean) => void;
}

export const useNotebookContextStore = create<NotebookContextState>((set) => ({
  insightsByNotebook: {},
  graphByNotebook: {},
  graphDirtyByNotebook: {},
  graphLoadingByNotebook: {},
  relatedByNote: {},
  relatedLoadingByNote: {},
  metaByNote: {},
  metaLoadingByNote: {},
  seedInsights: (notebookId, insights) =>
    set((state) => ({
      insightsByNotebook: { ...state.insightsByNotebook, [notebookId]: insights },
    })),
  setGraph: (notebookId, graph) =>
    set((state) => ({
      graphByNotebook: { ...state.graphByNotebook, [notebookId]: graph },
      graphDirtyByNotebook: { ...state.graphDirtyByNotebook, [notebookId]: false },
    })),
  setGraphLoading: (notebookId, loading) =>
    set((state) => ({
      graphLoadingByNotebook: { ...state.graphLoadingByNotebook, [notebookId]: loading },
    })),
  markContextDirty: (notebookId, dirty) =>
    set((state) => ({
      graphDirtyByNotebook: { ...state.graphDirtyByNotebook, [notebookId]: dirty },
    })),
  setRelated: (noteId, related) =>
    set((state) => ({
      relatedByNote: { ...state.relatedByNote, [noteId]: related },
    })),
  setRelatedLoading: (noteId, loading) =>
    set((state) => ({
      relatedLoadingByNote: { ...state.relatedLoadingByNote, [noteId]: loading },
    })),
  setMeta: (noteId, meta) =>
    set((state) => ({
      metaByNote: { ...state.metaByNote, [noteId]: meta },
    })),
  setMetaLoading: (noteId, loading) =>
    set((state) => ({
      metaLoadingByNote: { ...state.metaLoadingByNote, [noteId]: loading },
    })),
}));
