'use client';

import React, { createContext, useContext, useState, useEffect, useRef, useCallback, ReactNode } from 'react';

// ---- Types ----

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

interface Conversation {
    id: string;
    title: string;
    kb_id?: string;
    messages: ChatMessage[];
    updated_at: string;
}

export interface ChatMessage {
    role: 'user' | 'assistant';
    content: string;
    sources?: { source: string; page: number }[];
    isStreaming?: boolean;
    agent?: string;
    workflow?: WorkflowStep[];
}

export interface WorkflowStep {
    agent: string;
    status: 'working' | 'thinking' | 'done' | 'error';
    message: string;
    duration?: number;
}

interface AppState {
    kbs: KB[];
    conversations: Conversation[];
    selectedKbId: string | null;
    currentConversationId: string | null;
}

interface AppContextType extends AppState {
    setKbs: (kbs: KB[]) => void;
    setConversations: (convs: Conversation[]) => void;
    setSelectedKbId: (id: string | null) => void;
    setCurrentConversationId: (id: string | null) => void;
    refreshKbs: () => Promise<void>;
    refreshConversations: () => Promise<void>;
    // Global chat messages (survives page navigation)
    chatMessages: ChatMessage[];
    setChatMessages: (msgs: ChatMessage[]) => void;
    updateChatMessages: (updater: (prev: ChatMessage[]) => ChatMessage[]) => void;
    // Streaming state
    isChatStreaming: boolean;
    setIsChatStreaming: (v: boolean) => void;
    chatStatusMessage: string;
    setChatStatusMessage: (msg: string) => void;
    chatWorkflow: WorkflowStep[];
    setChatWorkflow: (steps: WorkflowStep[]) => void;
    chatCurrentAgent: string;
    setChatCurrentAgent: (agent: string) => void;
    // Abort controller for SSE
    abortStreamRef: React.MutableRefObject<AbortController | null>;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

const STORAGE_KEY = 'writingbot_state';

export function AppProvider({ children }: { children: ReactNode }) {
    const [kbs, setKbs] = useState<KB[]>([]);
    const [conversations, setConversations] = useState<Conversation[]>([]);
    const [selectedKbId, setSelectedKbIdState] = useState<string | null>(null);
    const [currentConversationId, setCurrentConversationIdState] = useState<string | null>(null);
    const [isHydrated, setIsHydrated] = useState(false);

    // **Global** chat messages — survive page navigation
    const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
    const [isChatStreaming, setIsChatStreaming] = useState(false);
    const [chatStatusMessage, setChatStatusMessage] = useState('正在思考...');
    const [chatWorkflow, setChatWorkflow] = useState<WorkflowStep[]>([]);
    const [chatCurrentAgent, setChatCurrentAgent] = useState('reasoner');
    const abortStreamRef = useRef<AbortController | null>(null);

    const updateChatMessages = useCallback(
        (updater: (prev: ChatMessage[]) => ChatMessage[]) => {
            setChatMessages((prev) => updater(prev));
        },
        []
    );

    // Load from localStorage on mount
    useEffect(() => {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved) {
            try {
                const parsed = JSON.parse(saved);
                if (parsed.selectedKbId) setSelectedKbIdState(parsed.selectedKbId);
                if (parsed.currentConversationId) setCurrentConversationIdState(parsed.currentConversationId);
            } catch (e) {
                console.error('Failed to parse saved state', e);
            }
        }
        setIsHydrated(true);
    }, []);

    // Save to localStorage
    useEffect(() => {
        if (isHydrated) {
            localStorage.setItem(STORAGE_KEY, JSON.stringify({
                selectedKbId,
                currentConversationId,
            }));
        }
    }, [selectedKbId, currentConversationId, isHydrated]);

    const setSelectedKbId = (id: string | null) => setSelectedKbIdState(id);
    const setCurrentConversationId = (id: string | null) => setCurrentConversationIdState(id);

    const refreshKbs = async () => {
        try {
            const res = await fetch('/api/kbs');
            const data = await res.json();
            if (data.success) setKbs(data.data);
        } catch (e) { console.error('Failed to fetch KBs', e); }
    };

    const refreshConversations = async () => {
        try {
            const res = await fetch('/api/conversations');
            const data = await res.json();
            if (data.success) setConversations(data.data);
        } catch (e) { console.error('Failed to fetch conversations', e); }
    };

    useEffect(() => {
        if (isHydrated) {
            refreshKbs();
            refreshConversations();
        }
    }, [isHydrated]);

    return (
        <AppContext.Provider value={{
            kbs, setKbs,
            conversations, setConversations,
            selectedKbId, setSelectedKbId,
            currentConversationId, setCurrentConversationId,
            refreshKbs, refreshConversations,
            chatMessages, setChatMessages, updateChatMessages,
            isChatStreaming, setIsChatStreaming,
            chatStatusMessage, setChatStatusMessage,
            chatWorkflow, setChatWorkflow,
            chatCurrentAgent, setChatCurrentAgent,
            abortStreamRef,
        }}>
            {children}
        </AppContext.Provider>
    );
}

export function useAppContext() {
    const context = useContext(AppContext);
    if (!context) throw new Error('useAppContext must be used within AppProvider');
    return context;
}
