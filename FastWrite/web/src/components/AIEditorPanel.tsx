import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  Bot,
  Check,
  Code,
  Cog,
  History,
  Loader2,
  Maximize2,
  Minimize2,
  RotateCcw,
  Search,
  Send,
  Sparkles,
  Trash2,
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
  TextItem,
} from '../types';
import { computeWordDiff } from '../utils/diff';
import { api } from '../api';
import DiffViewer from './DiffViewer';
import LLMSettingsModal from './LLMSettingsModal';

interface AIPanelProps {
  isOpen: boolean;
  selectedItemId: string | null;
  item: TextItem | null;
  fileContent: string;
  projectId: string;
  currentFilePath?: string;
  histories: Record<string, ChatMessage[]>;
  onHistoryChange: (histories: Record<string, ChatMessage[]>) => void;
  onClose: () => void;
  onResult: (result: DiffResult, modifiedContent: string, action: AIAction) => void;
  onContentChange?: (content: string) => void;
  onFullscreenChange?: (isFullscreen: boolean) => void;
  initialFullscreen?: boolean;
  editorRef?: React.RefObject<HTMLDivElement | null>;
  embedded?: boolean;
  canUndoLastKeep?: boolean;
  onUndoLastKeep?: () => void;
  projectKbId?: string;
  suggestedAction?: AIAction | null;
  suggestedDiagnostic?: CompileDiagnostic | null;
  suggestionSeed?: string;
}

interface ProjectPrompts {
  system: string;
  revise_selection: { user: string };
  proofread_section: { user: string };
  fix_compile_error: { user: string };
  generate_latex: { user: string };
  related_work: { user: string };
}

const ACTIONS: Array<{
  id: AIAction;
  label: string;
  icon: React.ReactNode;
  help: string;
}> = [
  {
    id: 'revise_selection',
    label: 'Revise',
    icon: <Wand2 size={14} className="text-blue-500" />,
    help: '改写当前选区，提升清晰度和表达。',
  },
  {
    id: 'proofread_section',
    label: 'Proofread',
    icon: <Check size={14} className="text-emerald-500" />,
    help: '对当前段落或章节做语言校对。',
  },
  {
    id: 'fix_compile_error',
    label: 'Fix Error',
    icon: <Zap size={14} className="text-amber-500" />,
    help: '结合编译报错，做最小修复。',
  },
  {
    id: 'generate_latex',
    label: 'Generate',
    icon: <Sparkles size={14} className="text-fuchsia-500" />,
    help: '依据上下文生成新的 LaTeX 草稿。',
  },
  {
    id: 'related_work',
    label: 'Related Work',
    icon: <Search size={14} className="text-violet-500" />,
    help: '结合知识库证据生成 related work 风格改写。',
  },
];

function getDefaultPrompt(action: AIAction, diagnostic?: CompileDiagnostic | null): string {
  switch (action) {
    case 'proofread_section':
      return 'Keep the meaning unchanged and improve readability.';
    case 'fix_compile_error':
      return diagnostic?.message ? `Fix this compile issue: ${diagnostic.message}` : 'Fix the compile issue with the smallest valid change.';
    case 'generate_latex':
      return 'Generate a polished LaTeX draft that fits this location.';
    case 'related_work':
      return 'Rewrite this as a related-work style paragraph using available evidence.';
    case 'revise_selection':
    default:
      return 'Revise this selection to be clearer and more precise.';
  }
}

function getActionLabel(action: AIAction): string {
  return ACTIONS.find((item) => item.id === action)?.label || action;
}

function getProjectPrompt(
  prompts: ProjectPrompts | null,
  action: AIAction,
  diagnostic?: CompileDiagnostic | null
): string {
  const projectPrompt = prompts?.[action]?.user?.trim();
  if (projectPrompt) return projectPrompt;
  return getDefaultPrompt(action, diagnostic);
}

const AIEditorPanel: React.FC<AIPanelProps> = ({
  isOpen,
  selectedItemId,
  item,
  projectId,
  currentFilePath,
  histories,
  onHistoryChange,
  onClose,
  onResult,
  onContentChange,
  onFullscreenChange,
  initialFullscreen = false,
  editorRef,
  embedded = false,
  canUndoLastKeep = false,
  onUndoLastKeep,
  projectKbId,
  suggestedAction,
  suggestedDiagnostic,
  suggestionSeed,
}) => {
  const [selectedAction, setSelectedAction] = useState<AIAction>('revise_selection');
  const [userPrompt, setUserPrompt] = useState('');
  const [useSystemPrompt, setUseSystemPrompt] = useState(true);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(initialFullscreen);
  const [showLLMSettings, setShowLLMSettings] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [showRawHistory, setShowRawHistory] = useState(false);
  const [fullscreenStyle, setFullscreenStyle] = useState<React.CSSProperties>({});
  const [projectPrompts, setProjectPrompts] = useState<ProjectPrompts | null>(null);
  const [aiResultContent, setAiResultContent] = useState<string | null>(null);
  const [aiExplanation, setAiExplanation] = useState('');
  const [aiReferences, setAiReferences] = useState<AISuggestionReference[]>([]);

  const promptTextareaRef = useRef<HTMLTextAreaElement>(null);
  const fullscreenTextareaRef = useRef<HTMLTextAreaElement>(null);

  const currentHistoryKey = `${currentFilePath || 'unknown'}:${selectedAction}`;
  const chatHistory = histories[currentHistoryKey] || [];

  const diff = useMemo(() => {
    if (!item || !aiResultContent) return null;
    return computeWordDiff(item.content, aiResultContent);
  }, [item, aiResultContent]);

  useEffect(() => {
    if (!projectId || !isOpen) return;
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
  }, [projectId, isOpen]);

  useEffect(() => {
    if (!editorRef?.current || !isFullscreen) {
      setFullscreenStyle({});
      return;
    }
    const rect = editorRef.current.getBoundingClientRect();
    setFullscreenStyle({
      position: 'fixed',
      top: rect.top,
      left: rect.left,
      width: rect.width,
      height: rect.height,
      zIndex: 60,
    });
  }, [editorRef, isFullscreen]);

  useEffect(() => {
    if (!suggestionSeed) return;
    if (suggestedAction) {
      setSelectedAction(suggestedAction);
      setUserPrompt(getProjectPrompt(projectPrompts, suggestedAction, suggestedDiagnostic));
    }
  }, [projectPrompts, suggestedAction, suggestedDiagnostic, suggestionSeed]);

  useEffect(() => {
    if (!promptTextareaRef.current) return;
    const textarea = promptTextareaRef.current;
    textarea.style.height = 'auto';
    textarea.style.height = `${Math.min(textarea.scrollHeight, 180)}px`;
  }, [userPrompt]);

  const addMessageToHistory = (message: ChatMessage) => {
    onHistoryChange({
      ...histories,
      [currentHistoryKey]: [...chatHistory, message],
    });
  };

  const clearCurrentHistory = () => {
    onHistoryChange({
      ...histories,
      [currentHistoryKey]: [],
    });
  };

  const handleRunAI = async () => {
    if (isProcessing || !item || !selectedItemId) return;
    if (selectedAction === 'related_work' && !projectKbId) {
      setAiExplanation('Related Work 动作需要项目绑定知识库（kbId）。当前项目尚未配置。');
      setAiResultContent(null);
      return;
    }

    const effectivePrompt = userPrompt.trim() || getProjectPrompt(projectPrompts, selectedAction, suggestedDiagnostic);

    addMessageToHistory({
      id: `${Date.now()}`,
      role: 'user',
      content: effectivePrompt,
      timestamp: new Date(),
    });

    setIsProcessing(true);
    setAiResultContent(null);
    setAiExplanation('');
    setAiReferences([]);

    try {
      const response = await fetch('/api/ai/process', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: selectedAction,
          content: item.content,
          projectId,
          filePath: currentFilePath,
          targetItemId: selectedItemId,
          lineStart: item.lineStart,
          lineEnd: item.lineStart + Math.max(item.content.split('\n').length - 1, 0),
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
        action?: AIAction;
        references?: AISuggestionReference[];
      };

      const resultAction = data.action || selectedAction;
      setSelectedAction(resultAction);
      setAiResultContent(data.content);
      setAiExplanation(data.explanation || `Prepared a ${getActionLabel(resultAction)} suggestion.`);
      setAiReferences(data.references || []);

      let modelName = data.model;
      if (!modelName) {
        try {
          const config = await api.getLLMConfig();
          modelName = config?.model;
        } catch (error) {
          console.error('Failed to fetch fallback model', error);
        }
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
      const message = error instanceof Error ? error.message : 'Failed to process AI request';
      setAiExplanation(message);
      setAiResultContent(null);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleApply = () => {
    if (!item || !selectedItemId || !aiResultContent || !diff) return;
    diff.itemId = selectedItemId;
    onResult(diff, aiResultContent, selectedAction);
    setAiResultContent(null);
    setAiExplanation('');
    setAiReferences([]);
  };

  const renderActionButtons = () => (
    <div className="flex flex-wrap items-center gap-1 rounded-lg bg-slate-100 p-1">
      {ACTIONS.map((action) => {
        const disabled = action.id === 'related_work' && !projectKbId;
        return (
          <button
            key={action.id}
            onClick={() => {
              setSelectedAction(action.id);
              if (!userPrompt.trim()) {
                setUserPrompt(getProjectPrompt(projectPrompts, action.id));
              }
            }}
            disabled={disabled}
            className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all ${
              selectedAction === action.id
                ? 'bg-white text-slate-800 shadow-sm'
                : 'text-slate-500 hover:text-slate-700'
            } ${disabled ? 'cursor-not-allowed opacity-40' : ''}`}
            title={disabled ? '需要为项目配置知识库后才能使用' : action.help}
          >
            {action.icon}
            {action.label}
          </button>
        );
      })}
    </div>
  );

  if (!isOpen) return null;

  const panelBody = (
    <div
      className={`flex flex-col bg-white ${
        isFullscreen
          ? ''
          : embedded
            ? 'relative mt-4 w-full rounded-b-lg border-t border-slate-100'
            : 'relative mt-2 w-full rounded-b-lg border border-slate-200 border-t-2 border-t-blue-500 shadow-lg'
      }`}
      style={isFullscreen ? fullscreenStyle : undefined}
    >
      {isFullscreen && item && (
        <textarea
          ref={fullscreenTextareaRef}
          value={item.content}
          onChange={(event) => onContentChange?.(event.target.value)}
          className="min-h-[160px] w-full flex-1 resize-none border-b border-slate-200 p-6 font-mono text-base outline-none"
        />
      )}

      <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-4 py-2">
        <div className="flex items-center gap-3">
          <h3 className="text-sm font-bold text-slate-700">AI Actions</h3>
          {renderActionButtons()}
        </div>

        <div className="flex items-center gap-2">
          {canUndoLastKeep && (
            <button
              onClick={onUndoLastKeep}
              className="rounded-md px-3 py-1.5 text-xs font-medium text-amber-700 transition-colors hover:bg-amber-50"
              title="Undo last keep"
            >
              <span className="inline-flex items-center gap-1.5">
                <RotateCcw size={14} />
                Undo Keep
              </span>
            </button>
          )}
          <button
            onClick={() => setShowHistory((value) => !value)}
            className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
              showHistory ? 'bg-blue-100 text-blue-700' : 'text-slate-600 hover:bg-slate-100'
            }`}
          >
            <span className="inline-flex items-center gap-1.5">
              <History size={14} />
              History ({chatHistory.length})
            </span>
          </button>
          <button
            onClick={() => setShowLLMSettings(true)}
            className="rounded-md p-1.5 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-800"
            title="Global AI settings"
          >
            <Cog size={18} />
          </button>
          <button
            onClick={() => {
              const next = !isFullscreen;
              setIsFullscreen(next);
              onFullscreenChange?.(next);
            }}
            className="rounded-md p-1.5 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-800"
            title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
          >
            {isFullscreen ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
          </button>
          <button
            onClick={() => {
              onClose();
              onFullscreenChange?.(false);
            }}
            className="rounded-md p-1.5 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-800"
            title="Close"
          >
            <X size={18} />
          </button>
        </div>
      </div>

      <div className="flex flex-1 flex-col">
        <div className="border-b border-slate-200 bg-white p-3">
          <div className="mb-2 flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
              <Bot size={14} />
              AI Assistant
            </div>
            <label className="flex items-center gap-2 text-xs text-slate-500">
              <input
                type="checkbox"
                checked={useSystemPrompt}
                onChange={(event) => setUseSystemPrompt(event.target.checked)}
                className="h-3.5 w-3.5 rounded border-slate-300 text-blue-600"
              />
              Include System Prompt
            </label>
          </div>

          {selectedAction === 'related_work' && !projectKbId && (
            <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
              当前项目未配置 `kbId`，因此无法使用 Related Work 动作。
            </div>
          )}

          {suggestedDiagnostic && selectedAction === 'fix_compile_error' && (
            <div className="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
              当前错误: {suggestedDiagnostic.message}
              {suggestedDiagnostic.line ? ` (line ${suggestedDiagnostic.line})` : ''}
            </div>
          )}

          <div className="flex gap-2">
            <textarea
              ref={promptTextareaRef}
              value={userPrompt}
              onChange={(event) => setUserPrompt(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  handleRunAI();
                }
              }}
              placeholder={getDefaultPrompt(selectedAction, suggestedDiagnostic)}
              className="min-h-[42px] flex-1 resize-none rounded-lg border border-slate-200 p-2.5 text-sm outline-none transition focus:border-blue-400 focus:ring-2 focus:ring-blue-500"
            />
            <button
              onClick={handleRunAI}
              disabled={isProcessing || (selectedAction === 'related_work' && !projectKbId)}
              className="inline-flex items-center gap-2 self-start rounded-lg bg-blue-600 px-4 py-2 text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isProcessing ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
              Run
            </button>
          </div>
        </div>

        {isProcessing && (
          <div className="flex flex-1 items-center justify-center bg-slate-50/70 p-8">
            <div className="flex flex-col items-center gap-3">
              <Loader2 size={28} className="animate-spin text-blue-500" />
              <p className="text-sm font-medium text-slate-500">Generating suggestion...</p>
            </div>
          </div>
        )}

        {!isProcessing && aiResultContent && diff && (
          <div className="flex flex-1 flex-col overflow-hidden border-t border-slate-200 bg-white">
            <div className="border-b border-slate-200 bg-slate-50 px-3 py-2">
              <div className="mb-2 flex items-start justify-between gap-4">
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wider text-slate-700">Suggested Changes</div>
                  <div className="mt-1 text-sm text-slate-600">{aiExplanation || 'Suggestion ready to review.'}</div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => {
                      setAiResultContent(null);
                      setAiExplanation('');
                      setAiReferences([]);
                    }}
                    className="rounded-md px-2 py-1 text-xs text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700"
                  >
                    Discard
                  </button>
                  <button
                    onClick={handleApply}
                    className="inline-flex items-center gap-1 rounded-md bg-green-600 px-3 py-1 text-xs font-medium text-white transition-colors hover:bg-green-700"
                  >
                    <Check size={12} />
                    Keep
                  </button>
                </div>
              </div>

              {aiReferences.length > 0 && (
                <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600">
                  <div className="mb-1 font-semibold text-slate-700">Evidence</div>
                  <div className="space-y-1">
                    {aiReferences.map((reference, index) => (
                      <div key={`${reference.source}-${index}`}>
                        [{index + 1}] {reference.source}
                        {reference.page ? ` p.${reference.page}` : ''}: {(reference.content || '').trim()}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="min-h-[180px] flex-1 overflow-auto">
              <DiffViewer
                originalContent={item?.content || ''}
                modifiedContent={aiResultContent}
                diff={diff}
                onAccept={handleApply}
                onReject={() => {
                  setAiResultContent(null);
                  setAiExplanation('');
                  setAiReferences([]);
                }}
                hideHeader={true}
              />
            </div>
          </div>
        )}

        {!isProcessing && !aiResultContent && (
          <div className="flex flex-1 flex-col items-center justify-center bg-slate-50/50 p-8 text-slate-400">
            <Bot size={32} className="mb-2 opacity-50" />
            <p className="text-sm font-medium">Ready to assist</p>
            <p className="text-xs text-center">
              {aiExplanation || 'Select an action, refine the instruction if needed, and run.'}
            </p>
          </div>
        )}
      </div>

      {showHistory && (
        <div className="absolute inset-x-4 bottom-4 top-14 z-[70] flex flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-2xl">
          <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-4 py-3">
            <h4 className="flex items-center gap-2 font-semibold text-slate-700">
              <History size={16} />
              Chat History
            </h4>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setShowRawHistory((value) => !value)}
                className={`rounded-md p-1 transition-colors ${
                  showRawHistory ? 'bg-blue-100 text-blue-600' : 'text-slate-400 hover:bg-slate-200 hover:text-slate-600'
                }`}
                title="View raw context"
              >
                <Code size={16} />
              </button>
              <button
                onClick={clearCurrentHistory}
                className="rounded-md p-1 text-slate-400 transition-colors hover:bg-red-50 hover:text-red-600"
                title="Clear conversation history"
              >
                <Trash2 size={16} />
              </button>
              <button
                onClick={() => setShowHistory(false)}
                className="rounded-md p-1 text-slate-400 transition-colors hover:bg-slate-200 hover:text-slate-600"
              >
                <X size={16} />
              </button>
            </div>
          </div>

          {showRawHistory ? (
            <div className="flex-1 overflow-auto bg-slate-900 p-4 font-mono text-xs text-slate-100 whitespace-pre-wrap">
              {JSON.stringify(
                {
                  system: projectPrompts?.system || '',
                  action: selectedAction,
                  messages: chatHistory,
                },
                null,
                2
              )}
            </div>
          ) : (
            <div className="flex-1 overflow-auto bg-white p-4">
              {chatHistory.length === 0 ? (
                <p className="py-8 text-center text-sm text-slate-400">No history yet</p>
              ) : (
                <div className="space-y-4">
                  {chatHistory.map((message) => (
                    <div key={message.id} className={`flex flex-col ${message.role === 'user' ? 'items-end' : 'items-start'}`}>
                      <div
                        className={`max-w-[90%] rounded-lg p-3 text-sm ${
                          message.role === 'user' ? 'bg-blue-100 text-blue-800' : 'bg-slate-100 text-slate-800'
                        }`}
                      >
                        {message.content}
                      </div>
                      <div className="mt-1 flex items-center gap-2 text-[10px] text-slate-400">
                        <span>{new Date(message.timestamp).toLocaleTimeString()}</span>
                        {message.role === 'ai' && message.model && (
                          <span className="rounded border border-slate-200 bg-slate-100 px-1 text-slate-500">
                            {message.model}
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      <LLMSettingsModal isOpen={showLLMSettings} onClose={() => setShowLLMSettings(false)} />
    </div>
  );

  return isFullscreen ? createPortal(panelBody, document.body) : panelBody;
};

export default AIEditorPanel;
