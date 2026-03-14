'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Bot, Loader2, MessageCircle, Plus, Send, Trash2, User } from 'lucide-react';

import MarkdownRenderer from '@/components/MarkdownRenderer';
import { useAppContext } from '@/context/AppContext';
import { ApiError, getConversation, listConversations, listSkills, removeConversation, streamChat } from '@/lib/chat';
import type { ChatMessage, ConversationDetail, ConversationSummary } from '@/types/chat';
import type { SkillItem } from '@/lib/chat';

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
    default_skill_ids: [],
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

function parseSlashQuery(text: string): string | null {
  const trimmed = text.trimStart();
  if (!trimmed.startsWith('/')) return null;
  return trimmed.slice(1).toLowerCase();
}

type ThinkingStepKey = 'plan' | 'retrieve' | 'synthesize' | 'critique' | 'finalize';
type ThinkingStepStatus = 'waiting' | 'working' | 'done' | 'skipped' | 'error';

interface ThinkingStep {
  key: ThinkingStepKey;
  label: string;
  status: ThinkingStepStatus;
  agent?: string;
}

const THINKING_STEP_ORDER: Array<{ key: ThinkingStepKey; label: string }> = [
  { key: 'plan', label: '问题规划' },
  { key: 'retrieve', label: '文献检索' },
  { key: 'synthesize', label: '方法对比' },
  { key: 'critique', label: '引用校验' },
  { key: 'finalize', label: '学术写作' },
];

function buildThinkingSteps(): ThinkingStep[] {
  return THINKING_STEP_ORDER.map((item) => ({ ...item, status: 'waiting' }));
}

function skillLabel(skill: SkillItem): string {
  return skill.label_cn || skill.name;
}

function skillDesc(skill: SkillItem): string {
  return skill.description_cn || skill.description;
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
  const [streamAgent, setStreamAgent] = useState<string>('');
  const [lastPaperHits, setLastPaperHits] = useState<number>(0);
  const [skills, setSkills] = useState<SkillItem[]>([]);
  const [loadingSkills, setLoadingSkills] = useState(false);
  const [selectedSkillId, setSelectedSkillId] = useState<string | null>(null);
  const [thinkingSteps, setThinkingSteps] = useState<ThinkingStep[]>(() => buildThinkingSteps());
  const [thinkingVisible, setThinkingVisible] = useState(false);
  const [streamStartedAt, setStreamStartedAt] = useState<number>(0);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [streamChars, setStreamChars] = useState(0);
  const [hasFirstChunk, setHasFirstChunk] = useState(false);

  const endRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const messages = useMemo(() => activeConversation.messages || [], [activeConversation]);
  const slashQuery = useMemo(() => parseSlashQuery(input), [input]);
  const visibleSkills = useMemo(() => {
    if (slashQuery === null) return [];
    if (!slashQuery) return skills;
    return skills.filter((skill) => {
      const haystacks = [skill.id, skill.name, skill.description, skill.label_cn || '', skill.description_cn || '']
        .join(' ')
        .toLowerCase();
      return haystacks.includes(slashQuery);
    });
  }, [slashQuery, skills]);
  const selectedSkill = useMemo(
    () => (selectedSkillId ? skills.find((skill) => skill.id === selectedSkillId) || null : null),
    [selectedSkillId, skills]
  );

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
    setSelectedSkillId(null);
    setPageError(null);
    setThinkingVisible(false);
    setThinkingSteps(buildThinkingSteps());
    setStreamAgent('');
    setLastPaperHits(0);
    setStreamStartedAt(0);
    setElapsedSeconds(0);
    setStreamChars(0);
    setHasFirstChunk(false);
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
        setSelectedSkillId((detail.default_skill_ids || [])[0] || null);
        setPageError(null);
        setThinkingVisible(false);
        setThinkingSteps(buildThinkingSteps());
        setStreamAgent('');
        setLastPaperHits(0);
        setStreamStartedAt(0);
        setElapsedSeconds(0);
        setStreamChars(0);
        setHasFirstChunk(false);
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
    const run = async () => {
      setLoadingSkills(true);
      try {
        const rows = await listSkills('research');
        setSkills(rows);
      } catch {
        setSkills([]);
      } finally {
        setLoadingSkills(false);
      }
    };
    void run();
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length, sending]);

  useEffect(() => {
    if (!activeConversationId) {
      setActiveConversation((prev) => ({ ...prev, kb_id: selectedKbId || null }));
    }
  }, [activeConversationId, selectedKbId]);

  useEffect(() => {
    if (!sending || !streamStartedAt) {
      setElapsedSeconds(0);
      return;
    }
    const t = window.setInterval(() => {
      const diff = Math.max(0, Math.floor((Date.now() - streamStartedAt) / 1000));
      setElapsedSeconds(diff);
    }, 250);
    return () => window.clearInterval(t);
  }, [sending, streamStartedAt]);

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
    if (chunk) {
      setHasFirstChunk(true);
      setStreamChars((prev) => prev + chunk.length);
    }
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

  const handleSelectSkill = (skillId: string) => {
    setSelectedSkillId(skillId);
    setInput((prev) => {
      const raw = prev.trimStart();
      if (!raw.startsWith('/')) return prev;
      const i = raw.indexOf(' ');
      if (i < 0) return '';
      return raw.slice(i + 1);
    });
    setTimeout(() => {
      textareaRef.current?.focus();
    }, 0);
  };

  const clearSkill = () => {
    setSelectedSkillId(null);
  };

  const updateThinkingStep = (step: ThinkingStepKey, status: ThinkingStepStatus, agent?: string) => {
    setThinkingSteps((prev) =>
      prev.map((item) => (item.key === step ? { ...item, status, agent: agent || item.agent } : item))
    );
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
      default_skill_ids: selectedSkillId ? [selectedSkillId] : [],
      updated_at: now,
      messages: [...prev.messages, userMessage, assistantPlaceholder],
    }));

    setSending(true);
    setPageError(null);
    setStreamAgent('');
    setLastPaperHits(0);
    setStreamStartedAt(Date.now());
    setElapsedSeconds(0);
    setStreamChars(0);
    setHasFirstChunk(false);
    setThinkingVisible(true);
    setThinkingSteps(buildThinkingSteps());
    updateThinkingStep('plan', 'working');
    if (!selectedKbId) {
      updateThinkingStep('retrieve', 'skipped');
    }

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
          skill_ids: selectedSkillId ? [selectedSkillId] : [],
        },
        {
          onChunk: appendAssistantChunk,
          onSources: (sources) => {
            setAssistantSources(sources);
            if (!selectedKbId || (sources || []).length === 0) {
              updateThinkingStep('retrieve', 'skipped');
            } else {
              updateThinkingStep('retrieve', 'done');
            }
            updateThinkingStep('synthesize', 'working');
          },
          onDone: (event) => {
            if (event.conversation_id) {
              finalConversationId = event.conversation_id;
            }
            setLastPaperHits(event.meta?.paper_hits || 0);
            setStreamAgent('');
            setStreamStartedAt(0);
            setThinkingSteps((prev) =>
              prev.map((item) => {
                if (item.status === 'error' || item.status === 'skipped' || item.status === 'done') return item;
                return { ...item, status: 'done' };
              })
            );
          },
          onError: (event) => {
            appendAssistantError(event.error || '请求失败');
            setStreamAgent('');
            setStreamStartedAt(0);
            setThinkingSteps((prev) =>
              prev.map((item) => {
                if (item.status === 'done' || item.status === 'skipped') return item;
                return { ...item, status: 'error' };
              })
            );
          },
          onEvent: (event) => {
            if (event.type === 'chunk') {
              if (event.meta?.agent_id) {
                setStreamAgent(event.meta.agent_id);
              }
              if (event.meta?.kind === 'progress') {
                const step = event.meta.step as ThinkingStepKey | undefined;
                const status = event.meta.status as ThinkingStepStatus | undefined;
                if (step && status) {
                  const mapped: ThinkingStepStatus = status === 'retry' ? 'working' : status;
                  updateThinkingStep(step, mapped, event.meta.agent_id);
                }
              }
            }
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
      setStreamStartedAt(0);
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
    <div className="h-full min-h-0 bg-slate-50 dark:bg-slate-900 p-2 md:p-3 transition-colors">
      <div className="h-full min-h-0 max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-[240px_1fr] gap-2.5">
        <div className="bg-white/95 dark:bg-slate-800/95 backdrop-blur rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm flex flex-col overflow-hidden min-h-0">
          <div className="p-2.5 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between">
            <div className="flex items-center gap-2 text-slate-700 dark:text-slate-200 font-semibold text-sm">
              <MessageCircle size={15} /> 会话
            </div>
            <button
              onClick={handleCreateConversation}
              className="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-blue-500 text-white text-xs hover:bg-blue-600 transition-colors"
              type="button"
            >
              <Plus size={13} /> 新建
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-1.5 min-h-0">
            <button
              type="button"
              onClick={openDraftConversation}
              className={`w-full text-left px-2 py-1.5 rounded-lg mb-1 border transition-colors ${
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
                    className={`w-full text-left px-2 py-1.5 rounded-lg mb-1 border transition-colors ${
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
          <div className="px-3 py-2 border-b border-slate-200 dark:border-slate-700 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
            <div>
              <h1 className="text-sm font-semibold text-slate-800 dark:text-white flex items-center gap-2">
                <MessageCircle size={16} className="text-blue-500" />
                {activeConversationId ? activeConversation.title || '智能对话' : '新聊天'}
              </h1>
              <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
                流式输出已开启，未发送内容不会保存为会话。
                {streamAgent ? ` 当前阶段：${streamAgent}` : ''}
                {lastPaperHits > 0 ? ` 命中论文：${lastPaperHits}` : ''}
              </p>
              {sending && (
                <div className="mt-1 inline-flex items-center gap-2 rounded-md border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/20 px-2 py-0.5 text-[11px] text-blue-700 dark:text-blue-200">
                  <span className="inline-block h-1.5 w-1.5 rounded-full bg-blue-500 animate-pulse" />
                  <span>{hasFirstChunk ? '正在生成中' : '模型准备中'}</span>
                  <span>已耗时 {elapsedSeconds}s</span>
                  <span>已接收 {streamChars} 字符</span>
                </div>
              )}
            </div>
            <select
              value={selectedKbId || ''}
              onChange={(e) => setSelectedKbId(e.target.value || null)}
              className="px-2.5 py-1.5 rounded-lg border border-slate-200 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-700 dark:text-slate-200 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
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

          {thinkingVisible && (
            <div className="mx-3 mt-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50/70 dark:bg-slate-800/60 px-2.5 py-2">
              <div className="mb-1.5 flex items-center justify-between text-[11px] text-slate-500 dark:text-slate-400">
                <span>智能体思考过程</span>
                <span>
                  进度{' '}
                  {Math.round(
                    (thinkingSteps.filter((item) => item.status === 'done' || item.status === 'skipped').length /
                      Math.max(1, thinkingSteps.length)) *
                      100
                  )}
                  %
                </span>
              </div>
              <div className="mb-2 h-1.5 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden">
                <div
                  className="h-full bg-blue-500 transition-all duration-300"
                  style={{
                    width: `${Math.round(
                      (thinkingSteps.filter((item) => item.status === 'done' || item.status === 'skipped').length /
                        Math.max(1, thinkingSteps.length)) *
                        100
                    )}%`,
                  }}
                />
              </div>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-1.5">
                {thinkingSteps.map((step) => (
                  <div
                    key={step.key}
                    className={`rounded-md border px-2 py-1.5 text-[11px] ${
                      step.status === 'working'
                        ? 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-700 dark:bg-blue-900/30 dark:text-blue-200'
                        : step.status === 'done'
                          ? 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-200'
                          : step.status === 'skipped'
                            ? 'border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-700 dark:bg-amber-900/20 dark:text-amber-200'
                            : step.status === 'error'
                              ? 'border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-700 dark:bg-rose-900/20 dark:text-rose-200'
                              : 'border-slate-200 bg-white text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400'
                    }`}
                  >
                    <div className="font-medium">{step.label}</div>
                    <div className="mt-0.5 opacity-80">
                      {step.status === 'waiting' && '等待中'}
                      {step.status === 'working' && '思考中...'}
                      {step.status === 'done' && '已完成'}
                      {step.status === 'skipped' && '已跳过（无本地证据）'}
                      {step.status === 'error' && '失败'}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="flex-1 overflow-y-auto p-3 space-y-2.5 min-h-0">
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
                const isStreamingPlaceholder =
                  !isUser && sending && idx === messages.length - 1 && !(msg.content || '').trim();
                return (
                  <div key={`${msg.timestamp}-${idx}`} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
                    <div
                      className={`max-w-[90%] rounded-2xl px-3 py-2 border ${
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
                      ) : isStreamingPlaceholder ? (
                        <div className="space-y-1.5 py-1">
                          <div className="h-2 w-32 rounded bg-slate-300/70 dark:bg-slate-600/70 animate-pulse" />
                          <div className="h-2 w-52 rounded bg-slate-300/60 dark:bg-slate-600/60 animate-pulse" />
                          <div className="h-2 w-40 rounded bg-slate-300/50 dark:bg-slate-600/50 animate-pulse" />
                        </div>
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

          <div className="px-3 py-2 border-t border-slate-200 dark:border-slate-700 bg-white/90 dark:bg-slate-800/90 backdrop-blur">
            {selectedSkill && (
              <div className="mb-1.5 flex items-center justify-between gap-2 rounded-lg border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/20 px-2 py-1.5">
                <div className="min-w-0">
                  <div className="text-[11px] font-medium text-blue-700 dark:text-blue-200">{skillLabel(selectedSkill)}</div>
                  <div className="text-[11px] text-blue-600/80 dark:text-blue-300/80 truncate">{skillDesc(selectedSkill)}</div>
                  <div className="text-[11px] text-blue-600/80 dark:text-blue-300/80 mt-0.5">已启用技能，直接输入你的问题即可发送</div>
                </div>
                <button
                  type="button"
                  onClick={clearSkill}
                  className="shrink-0 rounded-md border border-blue-300 dark:border-blue-700 px-2 py-0.5 text-[11px] text-blue-700 dark:text-blue-200 hover:bg-blue-100 dark:hover:bg-blue-900/40"
                >
                  更换技能
                </button>
              </div>
            )}
            {slashQuery !== null && !selectedSkill && (
              <div className="mb-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-1.5 max-h-36 overflow-y-auto">
                {loadingSkills ? (
                  <div className="text-[11px] text-slate-400 px-1 py-1">加载技能中...</div>
                ) : visibleSkills.length === 0 ? (
                  <div className="text-[11px] text-slate-400 px-1 py-1">未找到可用科研技能</div>
                ) : (
                  visibleSkills.map((skill) => (
                    <button
                      key={skill.id}
                      type="button"
                      onClick={() => handleSelectSkill(skill.id)}
                      className="w-full text-left px-2 py-1 rounded-md mb-1 text-[11px] border bg-transparent border-transparent hover:bg-slate-100 dark:hover:bg-slate-700/60 text-slate-600 dark:text-slate-200"
                    >
                      <div className="font-medium">{skillLabel(skill)}</div>
                      <div className="opacity-75 truncate">{skillDesc(skill)}</div>
                    </button>
                  ))
                )}
              </div>
            )}
            <div className="flex gap-2">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  // Avoid accidental submit while using IME composition.
                  if ((e.nativeEvent as { isComposing?: boolean }).isComposing) return;
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    void handleSend();
                  }
                }}
                rows={2}
                placeholder={selectedSkill ? '已选择技能，直接输入问题即可对话' : '输入问题；输入 / 可选择技能'}
                className="flex-1 px-2.5 py-2 rounded-lg border border-slate-200 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none text-sm"
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
