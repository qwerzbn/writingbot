'use client';

import { useEffect, useState, useRef, useCallback } from 'react';
import { useAppContext } from '@/context/AppContext';
import { Plus, Send, Loader2 } from 'lucide-react';

interface Message {
    role: 'user' | 'assistant';
    content: string;
    sources?: { source: string; page: number }[];
    isStreaming?: boolean;
}

interface Conversation {
    id: string;
    title: string;
    kb_id?: string;
    messages: Message[];
}

// 直接调用后端地址（绕过 Next.js 代理以支持 SSE 流式传输）
const API_BASE = 'http://localhost:5000';

export default function ChatPage() {
    const { kbs, refreshKbs, selectedKbId, setSelectedKbId, currentConversationId, setCurrentConversationId, conversations, refreshConversations } = useAppContext();
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState('');
    const [sending, setSending] = useState(false);
    const messagesEndRef = useRef<HTMLDivElement>(null);

    // 使用 ref 来追踪流式内容，避免 React 闭包问题
    const streamingContentRef = useRef('');

    useEffect(() => {
        refreshKbs();
        refreshConversations();
    }, []);

    useEffect(() => {
        if (currentConversationId) {
            loadConversation(currentConversationId);
        } else {
            setMessages([]);
        }
    }, [currentConversationId]);

    // Auto-scroll
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    const loadConversation = async (id: string) => {
        try {
            const res = await fetch(`/api/conversations/${id}`);
            const data = await res.json();
            if (data.success) {
                setMessages(data.data.messages || []);
                if (data.data.kb_id && !selectedKbId) {
                    setSelectedKbId(data.data.kb_id);
                }
            }
        } catch (e) {
            console.error(e);
        }
    };

    const handleNewChat = () => {
        setCurrentConversationId(null);
        setMessages([]);
    };

    const handleSelectConversation = (conv: Conversation) => {
        setCurrentConversationId(conv.id);
        if (conv.kb_id) setSelectedKbId(conv.kb_id);
    };

    // 更新最后一条消息的内容
    const updateLastMessage = useCallback((content: string, isStreaming: boolean, sources?: { source: string; page: number }[]) => {
        setMessages(prev => {
            const newMessages = prev.slice(0, -1);
            const lastMsg = prev[prev.length - 1];
            if (lastMsg && lastMsg.role === 'assistant') {
                newMessages.push({
                    ...lastMsg,
                    content,
                    isStreaming,
                    sources: sources ?? lastMsg.sources,
                });
            }
            return newMessages;
        });
    }, []);

    /**
     * Streaming send handler using SSE
     */
    const handleSend = async () => {
        if (!input.trim() || !selectedKbId) return;
        const userMessage = input.trim();
        setInput('');

        // 重置流式内容追踪
        streamingContentRef.current = '';

        // 1. 添加用户消息
        setMessages(prev => [...prev, { role: 'user', content: userMessage }]);

        // 2. 添加空的助手消息（显示加载指示器）
        setMessages(prev => [...prev, { role: 'assistant', content: '', isStreaming: true }]);
        setSending(true);

        try {
            // 3. 调用流式端点
            const res = await fetch(`${API_BASE}/api/chat/stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: userMessage,
                    conversation_id: currentConversationId,
                    kb_id: selectedKbId,
                }),
            });

            if (!res.ok) {
                throw new Error(`HTTP error: ${res.status}`);
            }

            const reader = res.body?.getReader();
            if (!reader) {
                throw new Error('No response body');
            }

            const decoder = new TextDecoder();
            let buffer = '';
            let receivedSources: { source: string; page: number }[] = [];
            let receivedConvId: string | null = null;

            // SSE 读取循环
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });

                // 解析 SSE 事件
                const lines = buffer.split('\n\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;

                    try {
                        const event = JSON.parse(line.slice(6));

                        switch (event.type) {
                            case 'chunk':
                                // 使用 ref 累积内容，避免闭包问题
                                streamingContentRef.current += event.content;
                                // 更新显示
                                updateLastMessage(streamingContentRef.current, true);
                                break;

                            case 'sources':
                                receivedSources = event.data;
                                break;

                            case 'done':
                                receivedConvId = event.conversation_id;
                                break;

                            case 'error':
                                updateLastMessage(`错误: ${event.error}`, false);
                                break;
                        }
                    } catch (e) {
                        console.error('Parse SSE error:', e);
                    }
                }
            }

            // 5. 完成：更新来源并移除流式标志
            updateLastMessage(streamingContentRef.current, false, receivedSources);

            // 更新会话 ID
            if (receivedConvId && !currentConversationId) {
                setCurrentConversationId(receivedConvId);
                refreshConversations();
            }

        } catch (e) {
            console.error('Stream error:', e);
            updateLastMessage(`网络错误: ${e}`, false);
        } finally {
            setSending(false);
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    return (
        <div className="h-full flex">
            {/* Conversation Sidebar */}
            <div className="w-64 bg-white border-r border-slate-200 flex flex-col shrink-0">
                <div className="h-18 px-4 flex items-center justify-between border-b border-slate-200">
                    <span className="font-semibold text-slate-800">KnowledgeHub</span>
                    <button
                        onClick={handleNewChat}
                        className="p-2 rounded-lg hover:bg-slate-100 text-slate-600"
                        title="新建对话"
                    >
                        <Plus size={18} />
                    </button>
                </div>
                <div className="flex-1 overflow-y-auto p-2">
                    {conversations.map((conv) => (
                        <div
                            key={conv.id}
                            onClick={() => handleSelectConversation(conv)}
                            className={`px-3 py-2 rounded-lg cursor-pointer text-sm truncate mb-1 transition-colors ${conv.id === currentConversationId
                                ? 'bg-blue-100 text-blue-700 font-medium'
                                : 'text-slate-600 hover:bg-slate-100'
                                }`}
                        >
                            {conv.title}
                        </div>
                    ))}
                </div>
            </div>

            {/* Chat Main */}
            <div className="flex-1 flex flex-col">
                {/* Header */}
                <header className="h-18 px-8 flex items-center justify-between bg-white border-b border-slate-200">
                    <h1 className="text-lg font-semibold text-slate-800">智能问答助手</h1>
                    <select
                        value={selectedKbId || ''}
                        onChange={(e) => setSelectedKbId(e.target.value || null)}
                        className="w-48 px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
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
                            <div className="text-5xl mb-4">💬</div>
                            <h2 className="text-xl font-medium text-slate-600 mb-2">开始新的对话</h2>
                            <p>请在右上角选择一个知识库，然后开始提问</p>
                        </div>
                    ) : (
                        messages.map((msg, idx) => (
                            <div
                                key={idx}
                                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                            >
                                <div
                                    className={`max-w-[75%] px-4 py-3 rounded-2xl ${msg.role === 'user'
                                        ? 'bg-blue-500 text-white rounded-br-sm'
                                        : 'bg-white border border-slate-200 text-slate-800 rounded-bl-sm'
                                        }`}
                                >
                                    <div className="whitespace-pre-wrap">
                                        {msg.content}
                                        {/* 打字机光标 */}
                                        {msg.isStreaming && msg.content && (
                                            <span className="inline-block w-2 h-4 bg-blue-500 ml-1 animate-pulse" />
                                        )}
                                    </div>
                                    {/* 等待中 */}
                                    {msg.isStreaming && !msg.content && (
                                        <div className="flex items-center gap-2 text-slate-400">
                                            <Loader2 size={16} className="animate-spin" />
                                            <span>正在思考...</span>
                                        </div>
                                    )}
                                    {/* 来源 */}
                                    {msg.sources && msg.sources.length > 0 && (
                                        <div className="mt-2 pt-2 border-t border-slate-200 text-xs text-slate-500">
                                            来源: {msg.sources.map((s) => `${s.source} (p.${s.page})`).join(', ')}
                                        </div>
                                    )}
                                </div>
                            </div>
                        ))
                    )}
                    <div ref={messagesEndRef} />
                </div>

                {/* Input */}
                <div className="p-4 bg-white border-t border-slate-200">
                    <div className="flex items-center gap-2 bg-slate-100 rounded-xl px-4 py-2">
                        <input
                            type="text"
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={handleKeyDown}
                            placeholder={selectedKbId ? '输入问题...' : '请先选择知识库'}
                            disabled={!selectedKbId || sending}
                            className="flex-1 bg-transparent outline-none text-slate-800 placeholder:text-slate-400"
                        />
                        <button
                            onClick={handleSend}
                            disabled={!input.trim() || !selectedKbId || sending}
                            className="p-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        >
                            {sending ? <Loader2 size={18} className="animate-spin" /> : <Send size={18} />}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}
