'use client';

import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';

interface KB {
  id: string;
  name: string;
  description?: string;
  embedding_model: string;
  embedding_provider?: string;
  files: FileInfo[];
  created_at: string;
}

interface FileInfo {
  id: string;
  name: string;
  size: number;
  chunks: number;
  uploaded_at: string;
}

interface AppContextType {
  kbs: KB[];
  setKbs: (kbs: KB[]) => void;
  selectedKbId: string | null;
  setSelectedKbId: (id: string | null) => void;
  refreshKbs: () => Promise<void>;
}

const AppContext = createContext<AppContextType | undefined>(undefined);
const STORAGE_KEY = 'writingbot_state';

function readSavedState(): { selectedKbId: string | null } {
  if (typeof window === 'undefined') return { selectedKbId: null };
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (!saved) return { selectedKbId: null };
    const parsed = JSON.parse(saved);
    return { selectedKbId: parsed.selectedKbId ?? null };
  } catch (e) {
    console.error('Failed to parse saved state', e);
    return { selectedKbId: null };
  }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [kbs, setKbs] = useState<KB[]>([]);
  const [selectedKbId, setSelectedKbIdState] = useState<string | null>(() => readSavedState().selectedKbId);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        selectedKbId,
      })
    );
  }, [selectedKbId]);

  const setSelectedKbId = (id: string | null) => setSelectedKbIdState(id);

  const refreshKbs = useCallback(async () => {
    try {
      const res = await fetch('/api/kbs');
      const data = await res.json();
      if (data.success) setKbs(data.data);
    } catch (e) {
      console.error('Failed to fetch KBs', e);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refreshKbs();
  }, [refreshKbs]);

  return (
    <AppContext.Provider
      value={{
        kbs,
        setKbs,
        selectedKbId,
        setSelectedKbId,
        refreshKbs,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}

export function useAppContext() {
  const context = useContext(AppContext);
  if (!context) throw new Error('useAppContext must be used within AppProvider');
  return context;
}
