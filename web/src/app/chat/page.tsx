'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Bot, Loader2, MessageCircle, Plus, Send, Trash2, User } from 'lucide-react';

import MarkdownRenderer from '@/components/MarkdownRenderer';
import { useAppContext } from '@/context/AppContext';
import { ApiError, getConversation, listConversations, removeConversation, streamChat } from '@/lib/chat';
import type { ChatMessage, ConversationDetail, ConversationSummary } from '@/types/chat';

const DRAFT_ID = '__draft__';

function nowIso(): string {
  return new Date().toISOString();
}

function createIdempotencyKey(seed: string): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `${seed}:${crypto.randomUUID()}`;
  }
  return `${seed}:${Date.now()}:${Math.random().toString(16).slice(2, 10)}`;
}

function buildDraftConversation(kbId: string | null): ConversationDetail {
  const now = nowIso();
  return {
    id: DRAFT_ID,
    title: '新聊天',
    kb_id: kbId,
    created_at: now,
    updated_at: now,
    messages: [],
  };
}

function normalizeConversations(rows: ConversationSummary[]): ConversationSummary[] {
  const unique = new Map<string, ConversationSummary>();
  for (const row of rows) {
    const messageCount = row.message_count ?? 0;
    const hasLastMessage = Boolean((row.last_message || '').trim());
    if (messageCount <= 0 && !hasLastMessage) {
      continue;
    }
    unique.set(row.id, row);
  }
  return Array.from(unique.values()).sort((a, b) =>
    String(b.updated_at || '').localeCompare(String(a.updated_at || ''))
  );
}

export default function ChatPage() {
  const { kbs, selectedKbId, setSelectedKbId } = useAppContext();

  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [activeConversation, setActiveConversation] = useState<ConversationDetail>(() =>
    buildDraftConversation(null)
  );
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [pageError, setPageError] = useState<string | null>(null);

  const endRef = useRef<HTMLDivElement | null>(null);

  const messages = useMemo(() => activeConversation.messages || [], [activeConversation]);

  const refreshConversations = useCallback(async () => {
    const rows = await listConversations();
    const normalized = normalizeConversations(rows);
    setConversations(normalized);

    if (activeConversationId && !normalized.some((row) => row.id === activeConversationId)) {
      setActiveConversationId(null);
      setActiveConversation(buildDraftConversation(selectedKbId || null));
    }
  }, [activeConversationId, selectedKbId]);

  const openDraftConversation = useCallback(() => {
    setActiveConversationId(null);
    setActiveConversation(buildDraftConversation(selectedKbId || null));
    setPageError(null);
  }, [selectedKbId]);

  const loadConversation = useCallback(
    async (convId: string) => {
      setLoadingDetail(true);
      try {
        const detail = await getConversation(convId);
        if (!detail.messages?.length) {
          await removeConversation(convId).catch(() => {});
          setConversations((prev) => prev.filter((row) => row.id !== convId));
          openDraftConversation();
          setPageError('检测到空会话，已自动清理并切换到新聊天。');
          return;
        }

        setActiveConversation(detail);
        setActiveConversationId(convId);
        setSelectedKbId(detail.kb_id || null);
        setPageError(null);
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) {
          setConversations((prev) => prev.filter((row) => row.id !== convId));
          openDraftConversation();
          setPageError('会话已不存在，已自动刷新列表。');
          return;
        }
        setPageError(error instanceof Error ? error.message : '加载会话失败');
        throw error;
      } finally {
        setLoadingDetail(false);
      }
    },
    [openDraftConversation, setSelectedKbId]
  );

  useEffect(() => {
    const run = async () => {
      setLoadingList(true);
      try {
        await refreshConversations();
        setPageError(null);
      } catch (error) {
        setPageError(error instanceof Error ? error.message : '加载会话列表失败');
      } finally {
        setLoadingList(false);
      }
    };

    void run();
  }, [refreshConversations]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length, sending]);

  useEffect(() => {
    if (!activeConversationId) {
      setActiveConversation((prev) => ({ ...prev, kb_id: selectedKbId || null }));
    }
  }, [activeConversationId, selectedKbId]);

  const handleCreateConversation = () => {
    if (!activeConversationId && activeConversation.messages.length === 0) {
      setInput('');
      setPageError(null);
      return;
    }
    openDraftConversation();
    setInput('');
  };

  const handleDeleteConversation = async (convId: string) => {
    try {
      await removeConversation(convId);
      setConversations((prev) => prev.filter((row) => row.id !== convId));

      if (activeConversationId === convId) {
        openDraftConversation();
      }

      setPageError(null);
    } catch (error) {
      setPageError(error instanceof Error ? error.message : '删除会话失败');
    }
  };

  const appendAssistantChunk = (chunk: string) => {
    setActiveConversation((prev) => {
      const next = [...prev.messages];
      for (let i = next.length - 1; i >= 0; i -= 1) {
        if (next[i].role === 'assistant') {
          next[i] = {
            ...next[i],
            content: `${next[i].content || ''}${chunk}`,
          };
          break;
        }
      }
      return { ...prev, messages: next, updated_at: nowIso() };
    });
  };

  const setAssistantSources = (sources: ChatMessage['sources']) => {
    setActiveConversation((prev) => {
      const next = [...prev.messages];
      for (let i = next.length - 1; i >= 0; i -= 1) {
        if (next[i].role === 'assistant') {
          next[i] = {
            ...next[i],
            sources,
          };
          break;
        }
      }
      return { ...prev, messages: next, updated_at: nowIso() };
    });
  };

  const appendAssistantError = (error: string) => {
    appendAssistantChunk(`\n\n> ${error}`);
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text || sending) return;

    setInput('');

    const now = nowIso();
    const trimmedTitle = text.slice(0, 30);
    const userMessage: ChatMessage = {
      role: 'user',
      content: text,
      timestamp: now,
      sources: [],
    };
    const assistantPlaceholder: ChatMessage = {
      role: 'assistant',
      content: '',
      timestamp: now,
      sources: [],
    };

    setActiveConversation((prev) => ({
      ...prev,
      title: prev.messages.length === 0 ? trimmedTitle || '新聊天' : prev.title,
      kb_id: selectedKbId ?? prev.kb_id,
      updated_at: now,
      messages: [...prev.messages, userMessage, assistantPlaceholder],
    }));

    setSending(true);
    setPageError(null);

    let finalConversationId = activeConversationId || undefined;
    const idempotencyKey = createIdempotencyKey(activeConversationId || DRAFT_ID);

    try {
      const done = await streamChat(
        {
          message: text,
          conversation_id: activeConversationId || undefined,
          kb_id: selectedKbId || undefined,
          title: activeConversation.messages.length === 0 ? trimmedTitle : undefined,
          idempotency_key: idempotencyKey,
        },
        {
          onChunk: appendAssistantChunk,
          onSources: setAssistantSources,
          onDone: (event) => {
            if (event.conversation_id) {
              finalConversationId = event.conversation_id;
            }
          },
          onError: (event) => {
            appendAssistantError(event.error || '请求失败');
          },
        }
      );

      if (done?.conversation_id) {
        finalConversationId = done.conversation_id;
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : '请求失败';
      appendAssistantError(msg);
      setPageError(msg);
    } finally {
      setSending(false);
    }

    if (finalConversationId) {
      setActiveConversationId(finalConversationId);
    }

    try {
      await refreshConversations();
      if (finalConversationId) {
        await loadConversation(finalConversationId);
      }
    } catch {
      // Keep local streamed content to avoid visible flicker.
    }
  };

  return (
    <div className="h-full min-h-0 bg-slate-50 dark:bg-slate-900 p-3 md:p-4 transition-colors">
      <div className="h-full min-h-0 max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-3">
        <div className="bg-white/95 dark:bg-slate-800/95 backdrop-blur rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm flex flex-col overflow-hidden min-h-0">
          <div className="p-3 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between">
            <div className="flex items-center gap-2 text-slate-700 dark:text-slate-200 font-semibold text-sm">
              <MessageCircle size={15} /> 会话
            </div>
            <button
              onClick={handleCreateConversation}
              className="inline-flex items-center gap-1 px-2 py-1.5 rounded-lg bg-blue-500 text-white text-xs hover:bg-blue-600 transition-colors"
              type="button"
            >
              <Plus size={13} /> 新建
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-2 min-h-0">
            <button
              type="button"
              onClick={openDraftConversation}
              className={`w-full text-left px-2.5 py-2 rounded-lg mb-1 border transition-colors ${
                activeConversationId === null
                  ? 'bg-blue-50 dark:bg-blue-900/25 border-blue-200 dark:border-blue-800'
                  : 'bg-transparent border-transparent hover:bg-slate-100 dark:hover:bg-slate-700/50'
              }`}
            >
              <div className="text-sm font-medium text-slate-700 dark:text-slate-200">新聊天</div>
              <div className="text-xs text-slate-400 mt-0.5 truncate">未发送内容不会保存</div>
            </button>

            {loadingList ? (
              <div className="h-20 flex items-center justify-center text-slate-400">
                <Loader2 size={16} className="animate-spin" />
              </div>
            ) : conversations.length === 0 ? (
              <div className="h-20 flex items-center justify-center text-xs text-slate-400 px-2 text-center">
                暂无已保存会话
              </div>
            ) : (
              conversations.map((conv) => {
                const active = conv.id === activeConversationId;
                return (
                  <div
                    key={conv.id}
                    className={`w-full text-left px-2.5 py-2 rounded-lg mb-1 border transition-colors ${
                      active
                        ? 'bg-blue-50 dark:bg-blue-900/25 border-blue-200 dark:border-blue-800'
                        : 'bg-transparent border-transparent hover:bg-slate-100 dark:hover:bg-slate-700/50'
                    }`}
                    onClick={() => void loadConversation(conv.id).catch(() => {})}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        void loadConversation(conv.id).catch(() => {});
                      }
                    }}
                  >
                    <div className="flex items-start gap-2">
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-slate-700 dark:text-slate-200 truncate">
                          {conv.title || '会话'}
                        </div>
                        <div className="text-xs text-slate-400 truncate mt-0.5">
                          {conv.last_message || '暂无内容'}
                        </div>
                      </div>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          void handleDeleteConversation(conv.id);
                        }}
                        className="p-1 rounded text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20"
                        type="button"
                        title="删除会话"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        <div className="bg-white/95 dark:bg-slate-800/95 backdrop-blur rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm flex flex-col overflow-hidden min-h-0">
          <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-700 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
            <div>
              <h1 className="text-base font-semibold text-slate-800 dark:text-white flex items-center gap-2">
                <MessageCircle size={16} className="text-blue-500" />
                {activeConversationId ? activeConversation.title || '智能对话' : '新聊天'}
              </h1>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                流式输出已开启，未发送内容不会保存为会话。
              </p>
            </div>
            <select
              value={selectedKbId || ''}
              onChange={(e) => setSelectedKbId(e.target.value || null)}
              className="px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-700 dark:text-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">不使用知识库（纯 LLM）</option>
              {kbs.map((kb) => (
                <option key={kb.id} value={kb.id}>
                  {kb.name}
                </option>
              ))}
            </select>
          </div>

          {pageError && (
            <div className="mx-4 mt-2 rounded-lg border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
              {pageError}
            </div>
          )}

          <div className="flex-1 overflow-y-auto p-4 space-y-3 min-h-0">
            {loadingDetail ? (
              <div className="h-full flex items-center justify-center text-slate-400">
                <Loader2 size={18} className="animate-spin" />
              </div>
            ) : messages.length === 0 ? (
              <div className="h-full flex items-center justify-center text-slate-400 text-sm">
                开始输入你的问题
              </div>
            ) : (
              messages.map((msg, idx) => {
                const isUser = msg.role === 'user';
                return (
                  <div key={`${msg.timestamp}-${idx}`} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
                    <div
                      className={`max-w-[86%] rounded-2xl px-3.5 py-2.5 border ${
                        isUser
                          ? 'bg-blue-500 border-blue-500 text-white'
                          : 'bg-slate-50 dark:bg-slate-700/40 border-slate-200 dark:border-slate-600 text-slate-800 dark:text-slate-100'
                      }`}
                    >
                      <div className="flex items-center gap-1.5 mb-1 text-[11px] opacity-80">
                        {isUser ? <User size={12} /> : <Bot size={12} />}
                        <span>{isUser ? '你' : '助手'}</span>
                      </div>

                      {isUser ? (
                        <div className="text-sm whitespace-pre-wrap break-words">{msg.content}</div>
                      ) : (
                        <MarkdownRenderer content={msg.content} sources={msg.sources || []} className="text-sm" />
                      )}
                    </div>
                  </div>
                );
              })
            )}
            <div ref={endRef} />
          </div>

          <div className="px-4 py-3 border-t border-slate-200 dark:border-slate-700 bg-white/90 dark:bg-slate-800/90 backdrop-blur">
            <div className="flex gap-2">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    void handleSend();
                  }
                }}
                rows={2}
                placeholder="输入问题，回车发送（Shift+Enter 换行）"
                className="flex-1 px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none text-sm"
              />
              <button
                onClick={() => void handleSend()}
                disabled={sending || !input.trim()}
                className="px-3 py-2 rounded-lg bg-blue-500 hover:bg-blue-600 text-white disabled:opacity-50 inline-flex items-center gap-1.5 transition-colors text-sm"
                type="button"
              >
                {sending ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
                发送
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
