import { create } from 'zustand';
import { persist } from 'zustand/middleware';

import type { NotebookKbOption, NotebookListRow, NotebookWorkspaceData } from '@/lib/notebook-api';

export type NotebookMobileTab = 'sources' | 'notes' | 'write' | 'context';
export type NotebookContextTab = 'insights' | 'graph' | 'related' | 'evidence';
export type NotebookEditorMode = 'edit' | 'split' | 'preview';

interface NotebookLayoutState {
  railCollapsed: boolean;
  notesCollapsed: boolean;
  contextCollapsed: boolean;
}

interface NotebookFilters {
  search: string;
  tag: string;
}

interface NotebookWorkspaceUiState {
  recentNotebookId: string | null;
  activeNotebookId: string | null;
  activeNotebook: NotebookWorkspaceData['notebook'] | null;
  notebooks: NotebookListRow[];
  kbOptions: NotebookKbOption[];
  railStats: NotebookWorkspaceData['rail']['stats'] | null;
  filtersByNotebook: Record<string, NotebookFilters>;
  mobileTabByNotebook: Record<string, NotebookMobileTab>;
  contextTabByNotebook: Record<string, NotebookContextTab>;
  editorModeByNotebook: Record<string, NotebookEditorMode>;
  layoutByNotebook: Record<string, NotebookLayoutState>;
  setWorkspaceSnapshot: (notebookId: string, data: NotebookWorkspaceData) => void;
  setRecentNotebookId: (notebookId: string | null) => void;
  setFilters: (notebookId: string, patch: Partial<NotebookFilters>) => void;
  setMobileTab: (notebookId: string, tab: NotebookMobileTab) => void;
  setContextTab: (notebookId: string, tab: NotebookContextTab) => void;
  setEditorMode: (notebookId: string, mode: NotebookEditorMode) => void;
  toggleLayout: (notebookId: string, key: keyof NotebookLayoutState) => void;
}

function getInitialLayout(): NotebookLayoutState {
  return {
    railCollapsed: false,
    notesCollapsed: false,
    contextCollapsed: false,
  };
}

function getInitialFilters(): NotebookFilters {
  return { search: '', tag: '' };
}

export const useNotebookWorkspaceUiStore = create<NotebookWorkspaceUiState>()(
  persist(
    (set) => ({
      recentNotebookId: null,
      activeNotebookId: null,
      activeNotebook: null,
      notebooks: [],
      kbOptions: [],
      railStats: null,
      filtersByNotebook: {},
      mobileTabByNotebook: {},
      contextTabByNotebook: {},
      editorModeByNotebook: {},
      layoutByNotebook: {},
      setWorkspaceSnapshot: (notebookId, data) =>
        set((state) => ({
          recentNotebookId: notebookId,
          activeNotebookId: notebookId,
          activeNotebook: data.notebook,
          notebooks: data.rail.notebooks,
          kbOptions: data.rail.kb_options,
          railStats: data.rail.stats,
          mobileTabByNotebook: {
            ...state.mobileTabByNotebook,
            [notebookId]:
              state.mobileTabByNotebook[notebookId] ?? data.view_state_defaults.mobile_tab ?? 'write',
          },
          contextTabByNotebook: {
            ...state.contextTabByNotebook,
            [notebookId]:
              state.contextTabByNotebook[notebookId] ?? data.view_state_defaults.context_tab ?? 'insights',
          },
          editorModeByNotebook: {
            ...state.editorModeByNotebook,
            [notebookId]:
              state.editorModeByNotebook[notebookId] ?? data.view_state_defaults.editor_mode ?? 'edit',
          },
          filtersByNotebook: {
            ...state.filtersByNotebook,
            [notebookId]: state.filtersByNotebook[notebookId] ?? getInitialFilters(),
          },
          layoutByNotebook: {
            ...state.layoutByNotebook,
            [notebookId]: state.layoutByNotebook[notebookId] ?? getInitialLayout(),
          },
        })),
      setRecentNotebookId: (recentNotebookId) => set({ recentNotebookId }),
      setFilters: (notebookId, patch) =>
        set((state) => ({
          filtersByNotebook: {
            ...state.filtersByNotebook,
            [notebookId]: {
              ...(state.filtersByNotebook[notebookId] ?? getInitialFilters()),
              ...patch,
            },
          },
        })),
      setMobileTab: (notebookId, tab) =>
        set((state) => ({
          mobileTabByNotebook: { ...state.mobileTabByNotebook, [notebookId]: tab },
        })),
      setContextTab: (notebookId, tab) =>
        set((state) => ({
          contextTabByNotebook: { ...state.contextTabByNotebook, [notebookId]: tab },
        })),
      setEditorMode: (notebookId, mode) =>
        set((state) => ({
          editorModeByNotebook: { ...state.editorModeByNotebook, [notebookId]: mode },
        })),
      toggleLayout: (notebookId, key) =>
        set((state) => ({
          layoutByNotebook: {
            ...state.layoutByNotebook,
            [notebookId]: {
              ...(state.layoutByNotebook[notebookId] ?? getInitialLayout()),
              [key]: !(state.layoutByNotebook[notebookId] ?? getInitialLayout())[key],
            },
          },
        })),
    }),
    {
      name: 'notebook-workspace-ui',
      partialize: (state) => ({
        recentNotebookId: state.recentNotebookId,
        filtersByNotebook: state.filtersByNotebook,
        mobileTabByNotebook: state.mobileTabByNotebook,
        contextTabByNotebook: state.contextTabByNotebook,
        editorModeByNotebook: state.editorModeByNotebook,
        layoutByNotebook: state.layoutByNotebook,
      }),
    }
  )
);
