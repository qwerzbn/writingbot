'use client';

import { useEffect, useState, useRef, useCallback } from 'react';
import { useAppContext, type ChatMessage, type WorkflowStep } from '@/context/AppContext';
import { Plus, Send, Loader2, Trash2, MessageSquare } from 'lucide-react';
import MarkdownRenderer from '@/components/MarkdownRenderer';
import AgentAvatar from '@/components/agents/AgentAvatar';
import AgentWorkflow from '@/components/agents/AgentWorkflow';
import { AGENTS } from '@/components/agents/AgentRegistry';
import dynamic from 'next/dynamic';
const PdfViewer = dynamic(() => import('@/components/chat/PdfViewer'), { ssr: false });
import { type CitationSource } from '@/components/chat/CitationCard';

// ---- Direct backend URL for SSE (bypass Next.js proxy to avoid buffering) ----
const STREAM_API = 'http://localhost:5001/api';

// ---- Slash commands ----

interface SlashCommand {
    command: string;
    label: string;
    description: string;
    prompt: string;
}

const SLASH_COMMANDS: SlashCommand[] = [
    { command: '/总结创新点', label: '总结创新点', description: '总结论文的核心创新和贡献', prompt: '@研究智能体 请总结当前知识库论文的核心创新点和主要贡献' },
    { command: '/文献综述', label: '文献综述', description: '生成涵盖所有论文的文献综述', prompt: '@研究智能体 请基于知识库中的论文，生成一篇结构化的文献综述' },
    { command: '/对比分析', label: '对比分析', description: '对比多篇论文的方法和结果', prompt: '@研究智能体 请对比分析知识库中论文的研究方法和实验结果' },
    { command: '/分析实验', label: '分析实验设计', description: '分析论文实验设计的优缺点', prompt: '请分析知识库中论文的实验设计，指出其优势和局限性' },
    { command: '/提取公式', label: '提取核心公式', description: '提取并解释论文中的关键公式', prompt: '请提取知识库论文中的核心数学公式并逐一解释' },
    { command: '/研究空白', label: '发现研究空白', description: '识别可能的研究方向和不足', prompt: '基于知识库论文，请识别当前研究的空白和未来可能的研究方向' },
];

// ---- @mention options ----

const MENTION_OPTIONS = Object.values(AGENTS).map((a) => ({
    id: a.id, name: a.name, emoji: a.emoji, description: a.description,
}));

// ---- Component ----

export default function ChatPage() {
    const {
        kbs, refreshKbs,
        selectedKbId, setSelectedKbId,
        currentConversationId, setCurrentConversationId,
        conversations, refreshConversations,
        // Global chat state
        chatMessages, setChatMessages, updateChatMessages,
        isChatStreaming, setIsChatStreaming,
        chatStatusMessage, setChatStatusMessage,
        chatWorkflow, setChatWorkflow,
        chatCurrentAgent, setChatCurrentAgent,
        abortStreamRef,
    } = useAppContext();

    // Local UI state only (menus, input)
    const inputRef = useRef<HTMLInputElement>(null);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const streamingContentRef = useRef('');
    const workflowRef = useRef<WorkflowStep[]>([]);

    // Menu state
    const [showMentionMenu, setShowMentionMenu] = useState(false);
    const [mentionFilter, setMentionFilter] = useState('');
    const [showSlashMenu, setShowSlashMenu] = useState(false);
    const [slashFilter, setSlashFilter] = useState('');
    const [input, setInput] = useState('');

    // PDF Viewer state
    const [activePdf, setActivePdf] = useState<{ url: string; name: string; page?: number } | null>(null);

    // Load conversation when switching
    useEffect(() => {
        if (currentConversationId && !isChatStreaming) {
            loadConversation(currentConversationId);
        } else if (!currentConversationId && !isChatStreaming) {
            setChatMessages([]);
        }
    }, [currentConversationId]);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [chatMessages, chatWorkflow]);

    const loadConversation = async (id: string) => {
        try {
            const res = await fetch(`/api/conversations/${id}`);
            const data = await res.json();
            if (data.success) {
                setChatMessages(data.data.messages || []);
                if (data.data.kb_id && !selectedKbId) {
                    setSelectedKbId(data.data.kb_id);
                }
            }
        } catch (e) { console.error(e); }
    };

    const handleNewChat = () => {
        // Abort any in-progress stream
        abortStreamRef.current?.abort();
        setCurrentConversationId(null);
        setChatMessages([]);
        setIsChatStreaming(false);
        setChatWorkflow([]);
        setActivePdf(null);
    };

    const handleSelectConversation = (conv: { id: string; kb_id?: string }) => {
        abortStreamRef.current?.abort();
        setIsChatStreaming(false);
        setChatWorkflow([]);
        setCurrentConversationId(conv.id);
        setActivePdf(null);
        if (conv.kb_id) setSelectedKbId(conv.kb_id);
    };

    const handleDeleteConversation = async (e: React.MouseEvent, convId: string) => {
        e.stopPropagation();
        if (!confirm('确定删除此对话？')) return;
        try {
            await fetch(`/api/conversations/${convId}`, { method: 'DELETE' });
            if (currentConversationId === convId) {
                setCurrentConversationId(null);
                setChatMessages([]);
            }
            refreshConversations();
        } catch (e) { console.error(e); }
    };

    // ---- Input handlers ----

    const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const val = e.target.value;
        setInput(val);

        const atMatch = val.match(/@(\S*)$/);
        if (atMatch) {
            setMentionFilter(atMatch[1]);
            setShowMentionMenu(true);
            setShowSlashMenu(false);
        } else {
            setShowMentionMenu(false);
        }

        if (val === '/' || val.match(/^\/\S*$/)) {
            setSlashFilter(val.slice(1));
            setShowSlashMenu(true);
            setShowMentionMenu(false);
        } else if (!val.startsWith('/')) {
            setShowSlashMenu(false);
        }
    };

    const selectMention = (agent: { id: string; name: string }) => {
        const beforeAt = input.replace(/@\S*$/, '');
        setInput(`@${agent.name} ${beforeAt}`);
        setShowMentionMenu(false);
        inputRef.current?.focus();
    };

    const selectSlashCommand = (cmd: SlashCommand) => {
        setInput(cmd.prompt);
        setShowSlashMenu(false);
        inputRef.current?.focus();
    };

    const filteredMentions = MENTION_OPTIONS.filter(
        (a) => !mentionFilter || a.name.includes(mentionFilter) || a.id.includes(mentionFilter)
    );

    const filteredSlashCommands = SLASH_COMMANDS.filter(
        (c) => !slashFilter || c.command.includes(slashFilter) || c.label.includes(slashFilter)
    );

    // ---- Streaming send (using global state) ----

    const handleSend = async () => {
        if (!input.trim() || !selectedKbId || isChatStreaming) return;
        const userMessage = input.trim();
        setInput('');
        setShowMentionMenu(false);
        setShowSlashMenu(false);

        streamingContentRef.current = '';
        workflowRef.current = [];
        setChatWorkflow([]);
        setChatCurrentAgent('reasoner');

        // Add messages to global state
        const newMessages: ChatMessage[] = [
            ...chatMessages,
            { role: 'user', content: userMessage },
            { role: 'assistant', content: '', isStreaming: true, workflow: [] },
        ];
        setChatMessages(newMessages);
        setIsChatStreaming(true);
        setChatStatusMessage('正在连接...');

        // Create abort controller
        const abortController = new AbortController();
        abortStreamRef.current = abortController;

        try {
            // *** DIRECT call to backend — bypass Next.js proxy for SSE ***
            const res = await fetch(`${STREAM_API}/chat/stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: userMessage,
                    conversation_id: currentConversationId,
                    kb_id: selectedKbId,
                }),
                signal: abortController.signal,
            });

            if (!res.ok) throw new Error(`HTTP ${res.status}`);

            const reader = res.body?.getReader();
            if (!reader) throw new Error('No response body');

            const decoder = new TextDecoder();
            let buffer = '';
            let receivedSources: { source: string; page: number }[] = [];

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const events = buffer.split('\n\n');
                buffer = events.pop() || '';

                for (const event of events) {
                    if (!event.startsWith('data: ')) continue;
                    try {
                        const ev = JSON.parse(event.slice(6));

                        switch (ev.type) {
                            case 'init':
                                // Persist conversation ID immediately
                                if (!currentConversationId && ev.conversation_id) {
                                    setCurrentConversationId(ev.conversation_id);
                                }
                                break;

                            case 'agent_step': {
                                const steps = [...workflowRef.current];
                                const existing = steps.findIndex(
                                    (s) => s.agent === ev.agent && (s.status === 'working' || s.status === 'thinking')
                                );
                                const step: WorkflowStep = {
                                    agent: ev.agent,
                                    status: ev.status,
                                    message: ev.message,
                                    duration: ev.duration,
                                };
                                if (existing >= 0) {
                                    steps[existing] = step;
                                } else {
                                    steps.push(step);
                                }
                                workflowRef.current = steps;
                                setChatWorkflow([...steps]);

                                if (ev.status === 'working' || ev.status === 'thinking') {
                                    setChatStatusMessage(ev.message);
                                }
                                break;
                            }

                            case 'chunk':
                                streamingContentRef.current += ev.content;
                                if (ev.agent) setChatCurrentAgent(ev.agent);
                                // Update the last message in global state
                                updateChatMessages((prev) => {
                                    const msgs = [...prev];
                                    const last = msgs[msgs.length - 1];
                                    if (last?.role === 'assistant') {
                                        msgs[msgs.length - 1] = {
                                            ...last,
                                            content: streamingContentRef.current,
                                            isStreaming: true,
                                            agent: ev.agent || last.agent,
                                            workflow: workflowRef.current,
                                        };
                                    }
                                    return msgs;
                                });
                                break;

                            case 'sources':
                                receivedSources = ev.data;
                                break;

                            case 'done':
                                break;

                            case 'error':
                                updateChatMessages((prev) => {
                                    const msgs = [...prev];
                                    const last = msgs[msgs.length - 1];
                                    if (last?.role === 'assistant') {
                                        msgs[msgs.length - 1] = {
                                            ...last,
                                            content: `错误: ${ev.error}`,
                                            isStreaming: false,
                                        };
                                    }
                                    return msgs;
                                });
                                break;
                        }
                    } catch (e) { console.error('Parse SSE:', e); }
                }
            }

            // Finalize
            updateChatMessages((prev) => {
                const msgs = [...prev];
                const last = msgs[msgs.length - 1];
                if (last?.role === 'assistant') {
                    msgs[msgs.length - 1] = {
                        ...last,
                        content: streamingContentRef.current,
                        isStreaming: false,
                        sources: receivedSources,
                        agent: chatCurrentAgent,
                        workflow: workflowRef.current,
                    };
                }
                return msgs;
            });

            refreshConversations();

        } catch (e: unknown) {
            if (e instanceof Error && e.name === 'AbortError') {
                // User navigated away or started new chat — keep partial content
                updateChatMessages((prev) => {
                    const msgs = [...prev];
                    const last = msgs[msgs.length - 1];
                    if (last?.role === 'assistant') {
                        msgs[msgs.length - 1] = {
                            ...last,
                            content: streamingContentRef.current || '(对话中断)',
                            isStreaming: false,
                        };
                    }
                    return msgs;
                });
            } else {
                console.error('Stream error:', e);
                updateChatMessages((prev) => {
                    const msgs = [...prev];
                    const last = msgs[msgs.length - 1];
                    if (last?.role === 'assistant') {
                        msgs[msgs.length - 1] = {
                            ...last,
                            content: `网络错误: ${e}`,
                            isStreaming: false,
                        };
                    }
                    return msgs;
                });
            }
        } finally {
            setIsChatStreaming(false);
            abortStreamRef.current = null;
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    // ---- Render ----

    const messages = chatMessages;

    return (
        <div className="h-full flex">
            {/* Conversation Sidebar */}
            <div className="w-64 bg-white dark:bg-slate-800 border-r border-slate-200 dark:border-slate-700 flex flex-col shrink-0">
                <div className="h-14 px-4 flex items-center justify-between border-b border-slate-200 dark:border-slate-700">
                    <span className="font-semibold text-slate-800 dark:text-white text-sm">对话列表</span>
                    <button onClick={handleNewChat} className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 transition-colors" title="新建对话">
                        <Plus size={18} />
                    </button>
                </div>
                <div className="flex-1 overflow-y-auto p-2">
                    {conversations.length === 0 ? (
                        <div className="text-center py-8 text-slate-400 text-sm">
                            <MessageSquare size={24} className="mx-auto mb-2 opacity-30" />
                            <p>暂无对话</p>
                            <p className="text-xs mt-1">选择知识库后开始提问</p>
                        </div>
                    ) : (
                        conversations.map((conv) => (
                            <div
                                key={conv.id}
                                onClick={() => handleSelectConversation(conv)}
                                className={`group px-3 py-2 rounded-lg cursor-pointer text-sm mb-1 transition-colors flex items-center justify-between ${conv.id === currentConversationId
                                    ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 font-medium'
                                    : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700'
                                    }`}
                            >
                                <span className="truncate flex-1">{conv.title}</span>
                                <button
                                    onClick={(e) => handleDeleteConversation(e, conv.id)}
                                    className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-red-100 dark:hover:bg-red-900/30 text-slate-400 hover:text-red-500 transition-all shrink-0 ml-1"
                                    title="删除对话"
                                >
                                    <Trash2 size={14} />
                                </button>
                            </div>
                        ))
                    )}
                </div>
            </div>

            {/* Chat Main */}
            <div className="flex-1 flex flex-col bg-slate-50 dark:bg-slate-900">
                {/* Header */}
                <header className="h-14 px-8 flex items-center justify-between bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700">
                    <div className="flex items-center gap-3">
                        <h1 className="text-lg font-semibold text-slate-800 dark:text-white">
                            WritingBot · 学术工作台
                        </h1>
                        <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-50 dark:bg-emerald-900/20 text-emerald-600 dark:text-emerald-400 text-xs">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                            {Object.keys(AGENTS).length} 个智能体就绪
                        </div>
                    </div>
                    <select
                        value={selectedKbId || ''}
                        onChange={(e) => setSelectedKbId(e.target.value || null)}
                        className="w-48 px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg text-sm bg-white dark:bg-slate-700 text-slate-700 dark:text-slate-200 focus:ring-2 focus:ring-blue-500 outline-none"
                    >
                        <option value="">选择知识库...</option>
                        {kbs.map((kb) => (
                            <option key={kb.id} value={kb.id}>{kb.name}</option>
                        ))}
                    </select>
                </header>

                {/* Messages */}
                <div className="flex-1 overflow-y-auto p-6 space-y-4">
                    {messages.length === 0 ? (
                        <div className="h-full flex flex-col items-center justify-center text-slate-400">
                            <div className="text-5xl mb-4">🤖</div>
                            <h2 className="text-xl font-medium text-slate-600 dark:text-slate-300 mb-2">
                                WritingBot · 学术工作台
                            </h2>
                            <p className="text-sm mb-6">多智能体协作，让学术研究更高效</p>
                            <div className="grid grid-cols-2 gap-2 max-w-md">
                                {Object.values(AGENTS).map((agent) => (
                                    <div key={agent.id} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-xs">
                                        <span className="text-base">{agent.emoji}</span>
                                        <div>
                                            <div className="font-medium text-slate-700 dark:text-slate-200">{agent.name}</div>
                                            <div className="text-slate-400 dark:text-slate-500">{agent.description}</div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                            <p className="text-xs mt-6 text-slate-400">
                                输入 <kbd className="px-1.5 py-0.5 bg-slate-200 dark:bg-slate-700 rounded text-xs">/</kbd> 快捷指令 · <kbd className="px-1.5 py-0.5 bg-slate-200 dark:bg-slate-700 rounded text-xs">@</kbd> 指定智能体
                            </p>
                        </div>
                    ) : (
                        messages.map((msg, idx) => (
                            <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                                <div className="max-w-[75%]">
                                    {/* Agent workflow */}
                                    {msg.role === 'assistant' && (msg.workflow?.length || (msg.isStreaming && chatWorkflow.length > 0)) ? (
                                        <AgentWorkflow
                                            steps={msg.isStreaming ? chatWorkflow : (msg.workflow || [])}
                                            isActive={!!msg.isStreaming}
                                        />
                                    ) : null}

                                    {/* Bubble */}
                                    <div className={`px-4 py-3 rounded-2xl ${msg.role === 'user'
                                        ? 'bg-blue-500 text-white rounded-br-sm'
                                        : 'bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-800 dark:text-slate-200 rounded-bl-sm'
                                        }`}>
                                        {msg.role === 'assistant' && msg.agent && !msg.isStreaming && (
                                            <div className="mb-2">
                                                <AgentAvatar agentId={msg.agent} showName />
                                            </div>
                                        )}

                                        {msg.role === 'user' ? (
                                            <div className="whitespace-pre-wrap">{msg.content}</div>
                                        ) : (
                                            <div>
                                                <MarkdownRenderer
                                                    content={msg.content}
                                                    sources={msg.sources}
                                                    onCitationClick={(source: CitationSource) => {
                                                        if (source.file_id && selectedKbId) {
                                                            setActivePdf({
                                                                url: `/api/kbs/${selectedKbId}/files/${source.file_id}/content`,
                                                                name: source.source,
                                                                page: typeof source.page === 'number' ? source.page : parseInt(String(source.page)) || 1
                                                            });
                                                        }
                                                    }}
                                                />
                                                {msg.isStreaming && msg.content && (
                                                    <span className="inline-block w-2 h-4 bg-blue-500 ml-1 animate-pulse" />
                                                )}
                                            </div>
                                        )}

                                        {msg.isStreaming && !msg.content && (
                                            <div className="flex items-center gap-2 text-slate-400">
                                                <Loader2 size={16} className="animate-spin" />
                                                <span className="text-sm">{chatStatusMessage}</span>
                                            </div>
                                        )}

                                        {msg.sources && msg.sources.length > 0 && (
                                            <div className="mt-2 pt-2 border-t border-slate-200 dark:border-slate-600 text-xs text-slate-500 dark:text-slate-400">
                                                📄 引用来源：{' '}
                                                {msg.sources.map((s, i) => (
                                                    <span key={i} className="inline-block mr-2 px-1.5 py-0.5 bg-slate-100 dark:bg-slate-700 rounded text-xs">
                                                        {s.source} (p.{s.page})
                                                    </span>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>
                        ))
                    )}
                    <div ref={messagesEndRef} />
                </div>

                {/* Input */}
                <div className="p-4 bg-white dark:bg-slate-800 border-t border-slate-200 dark:border-slate-700 relative">
                    {/* @mention popup */}
                    {showMentionMenu && filteredMentions.length > 0 && (
                        <div className="absolute bottom-full left-4 mb-2 w-72 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl shadow-xl overflow-hidden z-10">
                            <div className="px-3 py-2 text-xs text-slate-400 border-b border-slate-100 dark:border-slate-700">选择智能体</div>
                            {filteredMentions.map((a) => (
                                <button
                                    key={a.id}
                                    onClick={() => selectMention(a)}
                                    className="w-full px-3 py-2.5 flex items-center gap-3 hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors text-left"
                                >
                                    <span className="text-lg">{a.emoji}</span>
                                    <div>
                                        <div className="text-sm font-medium text-slate-700 dark:text-slate-200">{a.name}</div>
                                        <div className="text-xs text-slate-400">{a.description}</div>
                                    </div>
                                </button>
                            ))}
                        </div>
                    )}

                    {/* Slash popup */}
                    {showSlashMenu && filteredSlashCommands.length > 0 && (
                        <div className="absolute bottom-full left-4 mb-2 w-80 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl shadow-xl overflow-hidden z-10">
                            <div className="px-3 py-2 text-xs text-slate-400 border-b border-slate-100 dark:border-slate-700">⚡ 快捷指令</div>
                            {filteredSlashCommands.map((cmd) => (
                                <button
                                    key={cmd.command}
                                    onClick={() => selectSlashCommand(cmd)}
                                    className="w-full px-3 py-2.5 flex items-center gap-3 hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors text-left"
                                >
                                    <span className="text-sm font-mono text-blue-500 dark:text-blue-400 shrink-0">{cmd.command}</span>
                                    <div className="flex-1 min-w-0">
                                        <div className="text-sm text-slate-700 dark:text-slate-200">{cmd.label}</div>
                                        <div className="text-xs text-slate-400 truncate">{cmd.description}</div>
                                    </div>
                                </button>
                            ))}
                        </div>
                    )}

                    <div className="flex items-center gap-2 bg-slate-100 dark:bg-slate-700 rounded-xl px-4 py-2">
                        <input
                            ref={inputRef}
                            type="text"
                            value={input}
                            onChange={handleInputChange}
                            onKeyDown={handleKeyDown}
                            placeholder={selectedKbId ? '输入问题... 用 / 快捷指令 或 @ 指定智能体' : '请先选择知识库'}
                            disabled={!selectedKbId || isChatStreaming}
                            className="flex-1 bg-transparent outline-none text-slate-800 dark:text-white placeholder:text-slate-400 text-sm"
                        />
                        <button
                            onClick={handleSend}
                            disabled={!input.trim() || !selectedKbId || isChatStreaming}
                            className="p-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        >
                            {isChatStreaming ? <Loader2 size={18} className="animate-spin" /> : <Send size={18} />}
                        </button>
                    </div>
                </div>
            </div>

            {/* Split-screen PDF Viewer */}
            {activePdf && (
                <PdfViewer
                    fileUrl={activePdf.url}
                    fileName={activePdf.name}
                    initialPage={activePdf.page}
                    onClose={() => setActivePdf(null)}
                />
            )}
        </div>
    );
}

