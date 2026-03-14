import type {
  ChatDoneEvent,
  ChatErrorEvent,
  ChatSource,
  ChatStreamEvent,
  ConversationDetail,
  ConversationSummary,
} from '@/types/chat';

interface ApiSuccess<T> {
  success: boolean;
  data: T;
}

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

interface CreateConversationPayload {
  title?: string;
  kb_id?: string;
}

interface ChatRequestPayload {
  message: string;
  conversation_id?: string;
  kb_id?: string;
  title?: string;
  idempotency_key?: string;
}

interface StreamHandlers {
  onChunk?: (content: string) => void;
  onSources?: (sources: ChatSource[]) => void;
  onDone?: (event: ChatDoneEvent) => void;
  onError?: (event: ChatErrorEvent) => void;
  onEvent?: (event: ChatStreamEvent) => void;
}

async function readJson<T>(res: Response): Promise<T> {
  const data = (await res.json()) as T;
  return data;
}

async function throwApiError(res: Response): Promise<never> {
  let detail = '';
  try {
    const body = await res.json();
    detail = String(body?.detail || body?.error || '');
  } catch {
    detail = (await res.text()).trim();
  }
  throw new ApiError(res.status, detail || `Request failed (${res.status})`);
}

export async function listConversations(apiBase = ''): Promise<ConversationSummary[]> {
  const res = await fetch(`${apiBase}/api/conversations`);
  if (!res.ok) {
    await throwApiError(res);
  }
  const body = await readJson<ApiSuccess<ConversationSummary[]>>(res);
  return body.data || [];
}

export async function createConversation(payload: CreateConversationPayload, apiBase = ''): Promise<ConversationDetail> {
  const res = await fetch(`${apiBase}/api/conversations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    await throwApiError(res);
  }
  const body = await readJson<ApiSuccess<ConversationDetail>>(res);
  return body.data;
}

export async function getConversation(convId: string, apiBase = ''): Promise<ConversationDetail> {
  const res = await fetch(`${apiBase}/api/conversations/${convId}`);
  if (!res.ok) {
    await throwApiError(res);
  }
  const body = await readJson<ApiSuccess<ConversationDetail>>(res);
  return body.data;
}

export async function removeConversation(convId: string, apiBase = ''): Promise<void> {
  const res = await fetch(`${apiBase}/api/conversations/${convId}`, { method: 'DELETE' });
  if (!res.ok) {
    await throwApiError(res);
  }
}

export async function streamChat(
  payload: ChatRequestPayload,
  handlers: StreamHandlers,
  apiBase = ''
): Promise<ChatDoneEvent | null> {
  const runOnce = async (): Promise<ChatDoneEvent | null> => {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (payload.idempotency_key?.trim()) {
      headers['Idempotency-Key'] = payload.idempotency_key.trim();
    }

    const res = await fetch(`${apiBase}/api/chat/stream`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      await throwApiError(res);
    }

    const reader = res.body?.getReader();
    if (!reader) {
      throw new Error('No stream body');
    }

    const decoder = new TextDecoder();
    let buffer = '';
    let doneEvent: ChatDoneEvent | null = null;

    const dispatchRaw = (raw: string) => {
      if (!raw.trim()) return;
      try {
        const event = JSON.parse(raw) as ChatStreamEvent;
        handlers.onEvent?.(event);

        if (event.type === 'chunk') {
          handlers.onChunk?.(event.content);
        } else if (event.type === 'sources') handlers.onSources?.(event.data || []);
        else if (event.type === 'done') {
          doneEvent = event;
          handlers.onDone?.(event);
        } else if (event.type === 'error') {
          handlers.onError?.(event);
        }
      } catch {
        // Ignore malformed SSE fragments.
      }
    };

    const dispatchBlock = (block: string) => {
      if (!block.trim()) return;
      const dataLines: string[] = [];
      for (const line of block.split(/\r?\n/)) {
        if (line.startsWith('data:')) {
          dataLines.push(line.slice(5).trimStart());
        }
      }
      if (!dataLines.length) return;
      dispatchRaw(dataLines.join('\n'));
    };

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split(/\r?\n\r?\n/);
      buffer = events.pop() || '';

      for (const event of events) {
        dispatchBlock(event);
      }
    }

    if (buffer.trim()) {
      dispatchBlock(buffer);
    }

    return doneEvent;
  };

  const maxAttempts = payload.idempotency_key ? 2 : 1;
  let lastError: unknown = null;

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    try {
      const doneEvent = await runOnce();
      return doneEvent;
    } catch (error) {
      lastError = error;
      if (attempt >= maxAttempts) break;
      if (error instanceof ApiError && error.status >= 400 && error.status < 500 && error.status !== 409) {
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, 250 * attempt));
    }
  }

  throw lastError instanceof Error ? lastError : new Error('stream failed');
}
