export interface ChatSource {
  source: string;
  page: number | string;
  content?: string;
  score?: number;
  file_id?: string;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  sources: ChatSource[];
}

export interface ConversationSummary {
  id: string;
  title: string;
  kb_id?: string | null;
  default_skill_ids?: string[];
  created_at: string;
  updated_at: string;
  message_count?: number;
  last_message?: string;
}

export interface ConversationDetail {
  id: string;
  title: string;
  kb_id?: string | null;
  default_skill_ids?: string[];
  created_at: string;
  updated_at: string;
  messages: ChatMessage[];
}

export interface ChatChunkEvent {
  type: 'chunk';
  content: string;
  meta?: {
    agent_id?: string;
    skill_id?: string;
    paper_hits?: number;
  };
}

export interface ChatSourcesEvent {
  type: 'sources';
  data: ChatSource[];
  meta?: {
    paper_hits?: number;
  };
}

export interface ChatDoneEvent {
  type: 'done';
  conversation_id?: string;
  meta?: {
    paper_hits?: number;
    selected_skill_ids?: string[];
    skill_runs?: Array<{
      skill_id: string;
      status: string;
      critical?: boolean;
      error?: string;
      duration_ms?: number;
    }>;
  };
}

export interface ChatErrorEvent {
  type: 'error';
  error: string;
}

export type ChatStreamEvent = ChatChunkEvent | ChatSourcesEvent | ChatDoneEvent | ChatErrorEvent;
