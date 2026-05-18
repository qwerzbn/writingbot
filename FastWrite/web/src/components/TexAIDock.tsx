import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import {
  ChevronDown,
  ChevronUp,
  Check,
  History,
  Loader2,
  RotateCcw,
  Search,
  Send,
  Sparkles,
  Wand2,
  X,
  Zap,
} from 'lucide-react';

import type {
  AIAction,
  AISuggestionReference,
  ChatMessage,
  CompileDiagnostic,
  DiffResult,
  EditorAnchor,
  TexAIDockState,
} from '../types';
import { api } from '../api';
import { computeWordDiff } from '../utils/diff';
import DiffViewer from './DiffViewer';

interface ProjectPrompts {
  system: string;
  revise_selection: { user: string };
  proofread_section: { user: string };
  fix_compile_error: { user: string };
  generate_latex: { user: string };
  related_work: { user: string };
}

interface PendingSuggestion {
  action: AIAction;
  anchor: EditorAnchor;
  originalText: string;
  content: string;
  explanation: string;
  references: AISuggestionReference[];
}

interface TexAIDockProps {
  projectId: string;
  projectKbId?: string;
  currentFilePath?: string;
  activeAction: AIAction;
  anchor: EditorAnchor | null;
  histories: Record<string, ChatMessage[]>;
  onHistoryChange: (histories: Record<string, ChatMessage[]>) => void;
  onApplySuggestion: (payload: {
    action: AIAction;
    anchor: EditorAnchor;
    modifiedContent: string;
    diff: DiffResult;
  }) => void;
  canUndoLastKeep?: boolean;
  onUndoLastKeep?: () => void;
  suggestedDiagnostic?: CompileDiagnostic | null;
  suggestionSeed?: string;
  onOverlayInsetChange?: (inset: number) => void;
}

const ACTION_META: Record<AIAction, { label: string; help: string; icon: React.ReactNode }> = {
  revise_selection: {
    label: 'Revise',
    help: '改写当前选区，提高清晰度和表达。',
    icon: <Wand2 size={14} className="text-cyan-300" />,
  },
  proofread_section: {
    label: 'Proofread',
    help: '对当前目标做语言校对，尽量保持原意。',
    icon: <Check size={14} className="text-emerald-300" />,
  },
  fix_compile_error: {
    label: 'Fix Error',
    help: '结合当前编译错误做最小修复。',
    icon: <Zap size={14} className="text-amber-300" />,
  },
  generate_latex: {
    label: 'Generate',
    help: '基于上下文生成新的 LaTeX 内容。',
    icon: <Sparkles size={14} className="text-fuchsia-300" />,
  },
  related_work: {
    label: 'Related Work',
    help: '结合知识库证据生成 related work 风格改写。',
    icon: <Search size={14} className="text-violet-300" />,
  },
};

function getDefaultPrompt(action: AIAction, diagnostic?: CompileDiagnostic | null): string {
  switch (action) {
    case 'proofread_section':
      return 'Proofread this target and improve readability while preserving meaning.';
    case 'fix_compile_error':
      return diagnostic?.message
        ? `Fix this compile issue: ${diagnostic.message}`
        : 'Fix the compile issue with the smallest valid LaTeX change.';
    case 'generate_latex':
      return 'Generate polished LaTeX that fits naturally at this location.';
    case 'related_work':
      return 'Rewrite this into a concise related-work style paragraph grounded in available evidence.';
    case 'revise_selection':
    default:
      return 'Revise this selection to be clearer, tighter, and more precise.';
  }
}

function getProjectPrompt(
  prompts: ProjectPrompts | null,
  action: AIAction,
  diagnostic?: CompileDiagnostic | null
) {
  return prompts?.[action]?.user?.trim() || getDefaultPrompt(action, diagnostic);
}

const TexAIDock: React.FC<TexAIDockProps> = ({
  projectId,
  projectKbId,
  currentFilePath,
  activeAction,
  anchor,
  histories,
  onHistoryChange,
  onApplySuggestion,
  canUndoLastKeep = false,
  onUndoLastKeep,
  suggestedDiagnostic,
  suggestionSeed,
  onOverlayInsetChange,
}) => {
  const [dockState, setDockState] = useState<TexAIDockState>({
    action: activeAction,
    prompt: '',
    isProcessing: false,
  });
  const [isCollapsed, setIsCollapsed] = useState(true);
  const [projectPrompts, setProjectPrompts] = useState<ProjectPrompts | null>(null);
  const [pendingSuggestion, setPendingSuggestion] = useState<PendingSuggestion | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [useSystemPrompt, setUseSystemPrompt] = useState(true);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const promptRef = useRef<HTMLTextAreaElement>(null);
  const dockRef = useRef<HTMLDivElement>(null);
  const suggestionRef = useRef<HTMLDivElement>(null);

  const currentHistoryKey = `${currentFilePath || 'unknown'}:${activeAction}`;
  const chatHistory = histories[currentHistoryKey] || [];

  useEffect(() => {
    setDockState((prev) => ({ ...prev, action: activeAction }));
  }, [activeAction]);

  useEffect(() => {
    if (showHistory) {
      setIsCollapsed(false);
    }
  }, [showHistory]);

  useEffect(() => {
    if (pendingSuggestion) {
      setIsCollapsed(true);
      setShowHistory(false);
    }
  }, [pendingSuggestion]);

  useEffect(() => {
    if (!projectId) return;
    fetch(`/api/prompts/${projectId}`)
      .then((res) => res.json())
      .then((data: Record<string, any>) =>
        setProjectPrompts({
          system: data.system || '',
          revise_selection: data.revise_selection || { user: getDefaultPrompt('revise_selection') },
          proofread_section: data.proofread_section || { user: getDefaultPrompt('proofread_section') },
          fix_compile_error: data.fix_compile_error || { user: getDefaultPrompt('fix_compile_error') },
          generate_latex: data.generate_latex || { user: getDefaultPrompt('generate_latex') },
          related_work: data.related_work || { user: getDefaultPrompt('related_work') },
        })
      )
      .catch((error) => console.error('Failed to load project prompts:', error));
  }, [projectId]);

  useEffect(() => {
    const nextPrompt = getProjectPrompt(projectPrompts, activeAction, suggestedDiagnostic);
    setDockState((prev) => ({
      ...prev,
      prompt: nextPrompt,
    }));
    if (suggestedDiagnostic) {
      setStatusMessage(suggestedDiagnostic.message);
    }
  }, [projectPrompts, activeAction, suggestedDiagnostic, suggestionSeed]);

  useEffect(() => {
    if (!promptRef.current) return;
    promptRef.current.style.height = 'auto';
    promptRef.current.style.height = `${Math.min(promptRef.current.scrollHeight, 96)}px`;
  }, [dockState.prompt]);

  useLayoutEffect(() => {
    const measureInset = (element: HTMLDivElement | null) => {
      if (!element) return 0;
      const style = window.getComputedStyle(element);
      const bottom = Number.parseFloat(style.bottom || '0') || 0;
      return Math.ceil(element.getBoundingClientRect().height + bottom);
    };

    const updateInset = () => {
      const dockInset = measureInset(dockRef.current);
      const suggestionInset = measureInset(suggestionRef.current);
      const nextInset = Math.max(dockInset, suggestionInset, isCollapsed ? 80 : 132) + 20;
      onOverlayInsetChange?.(nextInset);
    };

    updateInset();

    const observers: ResizeObserver[] = [];
    for (const element of [dockRef.current, suggestionRef.current]) {
      if (!element) continue;
      const observer = new ResizeObserver(() => updateInset());
      observer.observe(element);
      observers.push(observer);
    }

    window.addEventListener('resize', updateInset);
    return () => {
      observers.forEach((observer) => observer.disconnect());
      window.removeEventListener('resize', updateInset);
    };
  }, [dockState.prompt, isCollapsed, onOverlayInsetChange, pendingSuggestion, showHistory, statusMessage, useSystemPrompt]);

  const diff = useMemo(() => {
    if (!pendingSuggestion) return null;
    return computeWordDiff(pendingSuggestion.originalText, pendingSuggestion.content);
  }, [pendingSuggestion]);

  const addMessageToHistory = (message: ChatMessage) => {
    onHistoryChange({
      ...histories,
      [currentHistoryKey]: [...chatHistory, message],
    });
  };

  const handleRunAI = async () => {
    if (dockState.isProcessing || !anchor) return;
    if (activeAction === 'related_work' && !projectKbId) {
      setStatusMessage('当前项目未配置 kbId，Related Work 动作不可用。');
      return;
    }

    const effectivePrompt = dockState.prompt.trim() || getProjectPrompt(projectPrompts, activeAction, suggestedDiagnostic);

    addMessageToHistory({
      id: `${Date.now()}`,
      role: 'user',
      content: effectivePrompt,
      timestamp: new Date(),
    });

    setDockState((prev) => ({ ...prev, isProcessing: true }));
    setPendingSuggestion(null);
    setStatusMessage(null);

    try {
      const response = await fetch('/api/ai/process', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: activeAction,
          content: anchor.selection.selectedText,
          projectId,
          filePath: currentFilePath,
          lineStart: anchor.selection.startLineNumber,
          lineEnd: anchor.selection.endLineNumber,
          targetItemId: `${anchor.selection.startOffset}:${anchor.selection.endOffset}`,
          systemPrompt: useSystemPrompt ? projectPrompts?.system : undefined,
          userPrompt: effectivePrompt,
          history: chatHistory.map((message) => ({
            role: message.role === 'ai' ? 'ai' : 'user',
            content: message.role === 'ai' && message.suggestion ? message.suggestion : message.content,
          })),
          diagnostic: suggestedDiagnostic,
          kbId: projectKbId,
        }),
      });

      if (!response.ok) {
        throw new Error(`AI request failed (${response.status})`);
      }

      const data = await response.json() as {
        content: string;
        explanation?: string;
        model?: string;
        references?: AISuggestionReference[];
      };

      setPendingSuggestion({
        action: activeAction,
        anchor,
        originalText: anchor.selection.selectedText,
        content: data.content,
        explanation: data.explanation || ACTION_META[activeAction].help,
        references: data.references || [],
      });
      setStatusMessage(data.explanation || 'Suggestion ready to review.');

      let modelName = data.model;
      if (!modelName) {
        const config = await api.getLLMConfig();
        modelName = config?.model;
      }

      addMessageToHistory({
        id: `${Date.now() + 1}`,
        role: 'ai',
        content: data.explanation || 'Suggestion ready to review.',
        suggestion: data.content,
        model: modelName,
        timestamp: new Date(),
      });
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : 'Failed to process AI request');
    } finally {
      setDockState((prev) => ({ ...prev, isProcessing: false }));
    }
  };

  const handleKeep = () => {
    if (!pendingSuggestion || !diff) return;
    diff.itemId = pendingSuggestion.anchor.rangeLabel;
    onApplySuggestion({
      action: pendingSuggestion.action,
      anchor: pendingSuggestion.anchor,
      modifiedContent: pendingSuggestion.content,
      diff,
    });
    setPendingSuggestion(null);
    setStatusMessage('Suggestion kept.');
  };

  const handleCompactSubmit = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== 'Enter') return;
    event.preventDefault();
    void handleRunAI();
  };

  return (
    <>
      {pendingSuggestion && diff && (
        <div
          ref={suggestionRef}
          className="pointer-events-auto absolute inset-x-4 bottom-30 z-20 overflow-hidden rounded-[24px] border border-white/12 bg-[#0B0B0B]/96 shadow-[0_24px_80px_rgba(0,0,0,0.45)] backdrop-blur"
        >
          <div className="flex items-center justify-between border-b border-white/8 px-4 py-3">
            <div>
              <div className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-300">Suggested Changes</div>
              <div className="mt-1 text-xs text-zinc-400">{pendingSuggestion.explanation}</div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPendingSuggestion(null)}
                className="rounded-full border border-white/10 px-3 py-1 text-[11px] font-medium text-zinc-300 transition-colors hover:border-white/20 hover:text-white"
              >
                Discard
              </button>
              <button
                onClick={handleKeep}
                className="inline-flex items-center gap-1.5 rounded-full bg-white px-3 py-1 text-[11px] font-semibold text-black transition-transform hover:scale-[1.02]"
              >
                <Check size={14} />
                Keep
              </button>
            </div>
          </div>

          {pendingSuggestion.references.length > 0 && (
            <div className="flex flex-wrap gap-2 border-b border-white/8 px-4 py-2.5">
              {pendingSuggestion.references.map((reference, index) => (
                <span
                  key={`${reference.source}-${index}`}
                  className="rounded-full border border-cyan-400/15 bg-cyan-400/10 px-3 py-1 text-[11px] text-cyan-100"
                  title={reference.content}
                >
                  [{index + 1}] {reference.source}{reference.page ? ` p.${reference.page}` : ''}
                </span>
              ))}
            </div>
          )}

          <div className="h-60 overflow-hidden bg-zinc-950/70">
            <DiffViewer
              originalContent={pendingSuggestion.originalText}
              modifiedContent={pendingSuggestion.content}
              diff={diff}
              onAccept={handleKeep}
              onReject={() => setPendingSuggestion(null)}
              hideHeader={true}
            />
          </div>
        </div>
      )}

      <div ref={dockRef} className="pointer-events-auto absolute inset-x-4 bottom-4 z-20">
        <div className="rounded-[24px] border border-white/10 bg-[#111111]/96 shadow-[0_20px_60px_rgba(0,0,0,0.45)] backdrop-blur">
          {isCollapsed ? (
            <div className="flex items-center gap-3 px-4 py-3">
              <button
                onClick={() => setIsCollapsed(false)}
                className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-[11px] font-medium text-white transition-colors hover:border-white/20 hover:bg-white/8"
              >
                {ACTION_META[activeAction].icon}
                {ACTION_META[activeAction].label}
              </button>

              <div className="min-w-0 flex-1 rounded-full border border-white/8 bg-black/35 px-4 py-2.5">
                <input
                  type="text"
                  value={dockState.prompt}
                  onChange={(event) => setDockState((prev) => ({ ...prev, prompt: event.target.value }))}
                  onKeyDown={handleCompactSubmit}
                  placeholder="随便提问"
                  className="w-full border-0 bg-transparent text-[14px] text-zinc-100 outline-none placeholder:text-zinc-500"
                />
              </div>

              <div className="flex shrink-0 items-center gap-2">
                <button
                  onClick={() => {
                    setIsCollapsed(false);
                    setShowHistory(true);
                  }}
                  className="inline-flex items-center gap-1 rounded-full border border-white/10 px-3 py-1.5 text-[11px] text-zinc-300 transition-colors hover:border-white/20 hover:text-white"
                >
                  <History size={12} />
                  {chatHistory.length > 0 ? chatHistory.length : 'History'}
                </button>
                <button
                  onClick={() => setIsCollapsed(false)}
                  className="inline-flex items-center gap-1 rounded-full border border-white/10 px-3 py-1.5 text-[11px] text-zinc-300 transition-colors hover:border-white/20 hover:text-white"
                >
                  <ChevronUp size={12} />
                  展开
                </button>
                <button
                  onClick={handleRunAI}
                  disabled={dockState.isProcessing || !anchor}
                  className="inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-[13px] font-semibold text-black transition-transform hover:scale-[1.02] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {dockState.isProcessing ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
                  {dockState.isProcessing ? 'Running' : 'Run'}
                </button>
              </div>
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between gap-3 px-4 pt-3">
                <div className="flex items-center gap-3">
                  <div className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] font-medium text-white">
                    {ACTION_META[activeAction].icon}
                    {ACTION_META[activeAction].label}
                  </div>
                  <span className="text-[11px] text-zinc-400">
                    {anchor ? `${anchor.rangeLabel} · ${anchor.source === 'selection' ? '选区' : anchor.source === 'diagnostic' ? '错误定位' : '当前上下文'}` : '未选择目标'}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setShowHistory((prev) => !prev)}
                    className="inline-flex items-center gap-1 rounded-full border border-white/10 px-3 py-1 text-[11px] text-zinc-300 transition-colors hover:border-white/20 hover:text-white"
                  >
                    <History size={12} />
                    History {chatHistory.length > 0 ? `(${chatHistory.length})` : ''}
                  </button>
                  <button
                    onClick={onUndoLastKeep}
                    disabled={!canUndoLastKeep}
                    className="inline-flex items-center gap-1 rounded-full border border-white/10 px-3 py-1 text-[11px] text-zinc-300 transition-colors hover:border-white/20 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <RotateCcw size={12} />
                    Undo Keep
                  </button>
                  <button
                    onClick={() => {
                      setShowHistory(false);
                      setIsCollapsed(true);
                    }}
                    className="inline-flex items-center gap-1 rounded-full border border-white/10 px-3 py-1 text-[11px] text-zinc-300 transition-colors hover:border-white/20 hover:text-white"
                  >
                    <ChevronDown size={12} />
                    收起
                  </button>
                </div>
              </div>

              {showHistory && (
                <div className="mx-4 mt-2 max-h-32 overflow-auto rounded-2xl border border-white/8 bg-black/30 px-4 py-3 text-xs text-zinc-300">
                  {chatHistory.length === 0 ? (
                    <div className="text-zinc-500">No history for this file/action yet.</div>
                  ) : (
                    <div className="space-y-3">
                      {chatHistory.slice(-6).map((message) => (
                        <div key={message.id} className="rounded-xl border border-white/6 bg-white/5 px-3 py-2">
                          <div className="mb-1 flex items-center justify-between text-[11px] uppercase tracking-wide text-zinc-500">
                            <span>{message.role}</span>
                            <span>{new Date(message.timestamp).toLocaleTimeString()}</span>
                          </div>
                          <div className="whitespace-pre-wrap text-zinc-200">{message.content}</div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              <div className="px-4 pb-3 pt-2">
                <div className="rounded-[20px] border border-white/8 bg-black/40 px-4 py-2.5">
                  <textarea
                    ref={promptRef}
                    value={dockState.prompt}
                    onChange={(event) => setDockState((prev) => ({ ...prev, prompt: event.target.value }))}
                    placeholder="随便提问"
                    className="min-h-[40px] w-full resize-none border-0 bg-transparent text-[15px] leading-6 text-zinc-100 outline-none placeholder:text-zinc-500"
                  />

                  <div className="mt-2 flex items-center justify-between gap-3">
                    <div className="flex min-w-0 items-center gap-3 text-[11px] text-zinc-400">
                      <label className="inline-flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={useSystemPrompt}
                          onChange={(event) => setUseSystemPrompt(event.target.checked)}
                          className="h-3.5 w-3.5 rounded border-white/20 bg-black/20"
                        />
                        Include System Prompt
                      </label>
                      {statusMessage && (
                        <span className="max-w-[380px] truncate text-zinc-400" title={statusMessage}>
                          {statusMessage}
                        </span>
                      )}
                    </div>

                    <button
                      onClick={handleRunAI}
                      disabled={dockState.isProcessing || !anchor}
                      className="inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-[13px] font-semibold text-black transition-transform hover:scale-[1.02] disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {dockState.isProcessing ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
                      {dockState.isProcessing ? 'Running' : 'Run'}
                    </button>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
};

export default TexAIDock;
