import React, {
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
  forwardRef,
} from 'react';
import Editor, { type OnMount } from '@monaco-editor/react';
import type * as Monaco from 'monaco-editor';
import {
  AlertTriangle,
  Bot,
  Check,
  ChevronDown,
  Clock,
  FileText,
  FolderOpen,
  History,
  Loader2,
  Search,
  Sparkles,
  Wand2,
  Wrench,
  Zap,
} from 'lucide-react';

import { api } from '../api';
import { ensureLatexMonaco, FASTWRITE_LATEX_LANGUAGE, FASTWRITE_LATEX_THEME } from '../editor/latexMonaco';
import type {
  AIAction,
  ChatMessage,
  CompileDiagnostic,
  DiffResult,
  DocumentRevision,
  EditorAnchor,
  EditorSelection,
  ProjectConfig,
  SelectedFile,
  SelectedProject,
} from '../types';
import BackupTimeline from './BackupTimeline';
import LLMSettingsModal from './LLMSettingsModal';
import TexAIDock from './TexAIDock';

type MonacoModule = typeof import('monaco-editor');

export interface MainEditorRef {
  getCurrentLine: () => number;
  getSelectedLineCount: () => number;
}

interface MainEditorProps {
  selectedFile: SelectedFile | null;
  selectedProject: SelectedProject | null;
  projectConfig?: ProjectConfig | null;
  diagnostics?: CompileDiagnostic[];
  scrollToLine?: number | null;
  onSyncToPDF?: (page: number, x: number, y: number) => void;
  onSaveSuccess?: () => void;
}

const ACTION_META: Record<
  AIAction,
  {
    label: string;
    description: string;
    icon: React.ComponentType<{ size?: number; className?: string }>;
  }
> = {
  revise_selection: {
    label: 'Revise',
    description: '改写当前选区，让表达更清晰、更紧凑。',
    icon: Wand2,
  },
  proofread_section: {
    label: 'Proofread',
    description: '校对当前上下文，尽量保持原意与 LaTeX 结构。',
    icon: Check,
  },
  fix_compile_error: {
    label: 'Fix Error',
    description: '结合诊断信息做最小修复。',
    icon: Zap,
  },
  generate_latex: {
    label: 'Generate',
    description: '在当前位置生成自然衔接的 LaTeX 内容。',
    icon: Sparkles,
  },
  related_work: {
    label: 'Related Work',
    description: '基于知识库证据生成 related work 风格文本。',
    icon: Search,
  },
};

function normalizeFilePath(path?: string | null): string {
  return (path || '').replace(/\/\.\//g, '/');
}

function isTexPath(path?: string | null): boolean {
  return (path || '').toLowerCase().endsWith('.tex');
}

function isRangeEmpty(range: Monaco.IRange): boolean {
  return (
    range.startLineNumber === range.endLineNumber &&
    range.startColumn === range.endColumn
  );
}

function rangeLabel(range: Monaco.IRange): string {
  return range.startLineNumber === range.endLineNumber
    ? `L${range.startLineNumber}`
    : `L${range.startLineNumber}-L${range.endLineNumber}`;
}

function isBlankLine(model: Monaco.editor.ITextModel, lineNumber: number): boolean {
  return model.getLineContent(lineNumber).trim().length === 0;
}

function findContextRange(
  model: Monaco.editor.ITextModel,
  monaco: MonacoModule,
  position: Monaco.IPosition
): Monaco.IRange {
  const lineCount = model.getLineCount();
  let targetLine = position.lineNumber;

  if (isBlankLine(model, targetLine)) {
    let up = targetLine - 1;
    while (up >= 1 && isBlankLine(model, up)) up -= 1;

    let down = targetLine + 1;
    while (down <= lineCount && isBlankLine(model, down)) down += 1;

    if (up >= 1) targetLine = up;
    else if (down <= lineCount) targetLine = down;
  }

  let startLine = targetLine;
  let endLine = targetLine;

  while (startLine > 1 && !isBlankLine(model, startLine - 1)) {
    startLine -= 1;
  }

  while (endLine < lineCount && !isBlankLine(model, endLine + 1)) {
    endLine += 1;
  }

  return new monaco.Range(startLine, 1, endLine, model.getLineMaxColumn(endLine));
}

function buildEditorSelection(
  model: Monaco.editor.ITextModel,
  range: Monaco.IRange,
  activeLine: number
): EditorSelection {
  const startOffset = model.getOffsetAt({
    lineNumber: range.startLineNumber,
    column: range.startColumn,
  });
  const endOffset = model.getOffsetAt({
    lineNumber: range.endLineNumber,
    column: range.endColumn,
  });

  return {
    startLineNumber: range.startLineNumber,
    startColumn: range.startColumn,
    endLineNumber: range.endLineNumber,
    endColumn: range.endColumn,
    startOffset,
    endOffset,
    selectedText: model.getValueInRange(range),
    activeLine,
  };
}

function buildAnchor(
  editor: Monaco.editor.IStandaloneCodeEditor,
  monaco: MonacoModule,
  source: EditorAnchor['source'],
  incomingRange?: Monaco.IRange
): EditorAnchor | null {
  const model = editor.getModel();
  if (!model) return null;

  const activePosition = editor.getPosition() || {
    lineNumber: 1,
    column: 1,
  };

  const selection = incomingRange || editor.getSelection() || new monaco.Range(1, 1, 1, 1);
  const effectiveRange =
    source === 'selection' && !isRangeEmpty(selection)
      ? selection
      : findContextRange(model, monaco, {
          lineNumber: selection.startLineNumber,
          column: selection.startColumn,
        });

  return {
    selection: buildEditorSelection(model, effectiveRange, activePosition.lineNumber),
    rangeLabel: rangeLabel(effectiveRange),
    source,
  };
}

function replaceSelectionInContent(
  content: string,
  selection: EditorSelection,
  nextText: string
): string {
  return (
    content.slice(0, selection.startOffset) +
    nextText +
    content.slice(selection.endOffset)
  );
}

function renderActionIcon(
  action: AIAction,
  className = 'text-zinc-200'
): React.ReactNode {
  const Icon = ACTION_META[action].icon;
  return <Icon size={15} className={className} />;
}

const MainEditor = forwardRef<MainEditorRef, MainEditorProps>(
  (
    {
      selectedFile,
      selectedProject,
      projectConfig,
      diagnostics = [],
      scrollToLine,
      onSaveSuccess,
    },
    ref
  ) => {
    const isTexFile = isTexPath(selectedFile?.path);

    const editorRef = useRef<Monaco.editor.IStandaloneCodeEditor | null>(null);
    const monacoRef = useRef<MonacoModule | null>(null);
    const textareaRef = useRef<HTMLTextAreaElement | null>(null);
    const toolsMenuRef = useRef<HTMLDivElement | null>(null);
    const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const saveStatusTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const aiSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const selectionDisposablesRef = useRef<Monaco.IDisposable[]>([]);
    const decorationIdsRef = useRef<string[]>([]);
    const flashDecorationIdsRef = useRef<string[]>([]);
    const pendingContentRef = useRef('');

    const [currentContent, setCurrentContent] = useState('');
    const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved'>('idle');
    const [isDirty, setIsDirty] = useState(false);
    const [showToolsMenu, setShowToolsMenu] = useState(false);
    const [showBackupTimeline, setShowBackupTimeline] = useState(false);
    const [showLLMSettings, setShowLLMSettings] = useState(false);
    const [activeAction, setActiveAction] = useState<AIAction>('revise_selection');
    const [activeAnchor, setActiveAnchor] = useState<EditorAnchor | null>(null);
    const [activeLine, setActiveLine] = useState(1);
    const [revisionStack, setRevisionStack] = useState<DocumentRevision[]>([]);
    const [suggestedDiagnostic, setSuggestedDiagnostic] = useState<CompileDiagnostic | null>(null);
    const [suggestionSeed, setSuggestionSeed] = useState('');
    const [aiHistories, setAiHistories] = useState<Record<string, ChatMessage[]>>({});
    const [isHistoryLoaded, setIsHistoryLoaded] = useState(false);
    const [editorBottomInset, setEditorBottomInset] = useState(176);

    const currentFileDiagnostics = useMemo(() => {
      if (!selectedFile) return [];
      const normalizedCurrentPath = normalizeFilePath(selectedFile.path);
      const basename = selectedFile.name;
      return diagnostics.filter((diagnostic) => {
        if (!diagnostic.filePath) return true;
        const normalizedDiagnosticPath = normalizeFilePath(diagnostic.filePath);
        return (
          normalizedDiagnosticPath === normalizedCurrentPath ||
          normalizedDiagnosticPath.endsWith(`/${basename}`) ||
          normalizedCurrentPath.endsWith(`/${normalizedDiagnosticPath.split('/').pop() || ''}`)
        );
      });
    }, [diagnostics, selectedFile]);

    const lineDiagnostics = useMemo(
      () => currentFileDiagnostics.filter((diagnostic) => typeof diagnostic.line === 'number'),
      [currentFileDiagnostics]
    );
    const projectDiagnostics = useMemo(
      () => currentFileDiagnostics.filter((diagnostic) => typeof diagnostic.line !== 'number'),
      [currentFileDiagnostics]
    );

    const diagnosticsByLine = useMemo(() => {
      const map = new Map<number, CompileDiagnostic[]>();
      for (const diagnostic of lineDiagnostics) {
        if (!diagnostic.line) continue;
        const bucket = map.get(diagnostic.line) || [];
        bucket.push(diagnostic);
        map.set(diagnostic.line, bucket);
      }
      return map;
    }, [lineDiagnostics]);

    const saveIndicator = useMemo(() => {
      if (saveStatus === 'saving') {
        return (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-cyan-400/20 bg-cyan-400/10 px-2.5 py-1 text-[10px] font-medium text-cyan-100">
            <Loader2 size={11} className="animate-spin" />
            Saving
          </span>
        );
      }
      if (isDirty) {
        return (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-400/20 bg-amber-400/10 px-2.5 py-1 text-[10px] font-medium text-amber-100">
            <span className="h-1.5 w-1.5 rounded-full bg-amber-300" />
            Unsaved
          </span>
        );
      }
      return (
        <span className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[10px] font-medium text-zinc-300">
          <Check size={11} />
          Saved
        </span>
      );
    }, [isDirty, saveStatus]);

    const updateAnchorFromEditor = useCallback(
      (source?: EditorAnchor['source'], incomingRange?: Monaco.IRange) => {
        if (!editorRef.current || !monacoRef.current || !isTexFile) return;
        const anchor = buildAnchor(
          editorRef.current,
          monacoRef.current,
          source || (incomingRange && !isRangeEmpty(incomingRange) ? 'selection' : 'cursor-block'),
          incomingRange
        );
        if (!anchor) return;
        setActiveAnchor(anchor);
        setActiveLine(anchor.selection.activeLine);
      },
      [isTexFile]
    );

    const persistContent = useCallback(
      async (content: string) => {
        if (!selectedFile || !selectedProject) return false;

        if (saveStatusTimerRef.current) clearTimeout(saveStatusTimerRef.current);
        setSaveStatus('saving');

        try {
          const success = await api.writeFile(
            selectedFile.path,
            content,
            selectedProject.project.id,
            true
          );
          if (!success) {
            throw new Error('Write request was rejected');
          }
          pendingContentRef.current = content;
          setIsDirty(false);
          setSaveStatus('saved');
          saveStatusTimerRef.current = setTimeout(() => setSaveStatus('idle'), 1800);
          onSaveSuccess?.();
          return true;
        } catch (error) {
          console.error('Auto-save failed:', error);
          setSaveStatus('idle');
          return false;
        }
      },
      [onSaveSuccess, selectedFile, selectedProject]
    );

    const debouncedSave = useCallback(async () => {
      await persistContent(pendingContentRef.current);
    }, [persistContent]);

    const scheduleSave = useCallback(
      (content: string) => {
        pendingContentRef.current = content;
        setIsDirty(true);
        setSaveStatus('idle');
        if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
        saveTimerRef.current = setTimeout(() => {
          void debouncedSave();
        }, 3000);
      },
      [debouncedSave]
    );

    const handleContentChange = useCallback(
      (nextValue: string) => {
        setCurrentContent(nextValue);
        scheduleSave(nextValue);
      },
      [scheduleSave]
    );

    const handleUndoLastKeep = useCallback(() => {
      const lastRevision = revisionStack[revisionStack.length - 1];
      if (!lastRevision) return;

      setCurrentContent(lastRevision.previousContent);
      pendingContentRef.current = lastRevision.previousContent;
      scheduleSave(lastRevision.previousContent);
      setRevisionStack((prev) => prev.slice(0, -1));

      window.requestAnimationFrame(() => {
        if (!editorRef.current || !monacoRef.current) return;
        const { selection } = lastRevision.anchor;
        const range = new monacoRef.current.Range(
          selection.startLineNumber,
          selection.startColumn,
          selection.endLineNumber,
          selection.endColumn
        );
        editorRef.current.setSelection(range);
        editorRef.current.revealLineInCenter(selection.activeLine);
        updateAnchorFromEditor(lastRevision.anchor.source, range);
      });
    }, [revisionStack, scheduleSave, updateAnchorFromEditor]);

    const handleApplySuggestion = useCallback(
      ({
        action,
        anchor,
        modifiedContent,
      }: {
        action: AIAction;
        anchor: EditorAnchor;
        modifiedContent: string;
        diff: DiffResult;
      }) => {
        const nextContent = replaceSelectionInContent(
          currentContent,
          anchor.selection,
          modifiedContent
        );

        setRevisionStack((prev) => [
          ...prev,
          {
            id: `${Date.now()}`,
            action,
            previousContent: currentContent,
            nextContent,
            anchor,
            createdAt: new Date().toISOString(),
          },
        ]);

        setCurrentContent(nextContent);
        scheduleSave(nextContent);
        setSuggestedDiagnostic(null);
        setSuggestionSeed('');

        window.requestAnimationFrame(() => {
          if (!editorRef.current || !monacoRef.current) return;
          const model = editorRef.current.getModel();
          if (!model) return;

          const startPosition = model.getPositionAt(anchor.selection.startOffset);
          const endOffset = anchor.selection.startOffset + modifiedContent.length;
          const endPosition = model.getPositionAt(endOffset);
          const nextRange = new monacoRef.current.Range(
            startPosition.lineNumber,
            startPosition.column,
            endPosition.lineNumber,
            endPosition.column
          );
          editorRef.current.setSelection(nextRange);
          editorRef.current.revealLineInCenter(startPosition.lineNumber);
          updateAnchorFromEditor('selection', nextRange);
        });
      },
      [currentContent, scheduleSave, updateAnchorFromEditor]
    );

    const openDiagnosticFix = useCallback(
      (diagnostic: CompileDiagnostic) => {
        if (!editorRef.current || !monacoRef.current || !isTexFile) return;
        const targetLine = diagnostic.line || activeLine || 1;
        const range = new monacoRef.current.Range(targetLine, 1, targetLine, 1);

        editorRef.current.setPosition({ lineNumber: targetLine, column: 1 });
        editorRef.current.revealLineInCenter(targetLine);
        setActiveAction('fix_compile_error');
        setSuggestedDiagnostic(diagnostic);
        setSuggestionSeed(`${diagnostic.id}-${Date.now()}`);
        updateAnchorFromEditor('diagnostic', range);
      },
      [activeLine, isTexFile, updateAnchorFromEditor]
    );

    useEffect(() => {
      if (!selectedProject?.project.id) return;

      setIsHistoryLoaded(false);
      setAiHistories({});

      fetch(`/api/projects/${selectedProject.project.id}/ai-cache`)
        .then((response) => response.json())
        .then((data: Record<string, ChatMessage[]> & { error?: string }) => {
          if (data && !data.error) {
            const { error: _error, ...histories } = data;
            setAiHistories(histories);
          }
          setIsHistoryLoaded(true);
        })
        .catch((error) => {
          console.error('Failed to load AI cache:', error);
          setIsHistoryLoaded(true);
        });
    }, [selectedProject?.project.id]);

    useEffect(() => {
      if (!selectedProject?.project.id || !isHistoryLoaded) return;

      if (aiSaveTimerRef.current) clearTimeout(aiSaveTimerRef.current);
      aiSaveTimerRef.current = setTimeout(() => {
        fetch(`/api/projects/${selectedProject.project.id}/ai-cache`, {
          method: 'POST',
          body: JSON.stringify(aiHistories),
        }).catch((error) => console.error('Failed to save AI cache', error));
      }, 2000);

      return () => {
        if (aiSaveTimerRef.current) clearTimeout(aiSaveTimerRef.current);
      };
    }, [aiHistories, isHistoryLoaded, selectedProject?.project.id]);

    useEffect(() => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      if (saveStatusTimerRef.current) clearTimeout(saveStatusTimerRef.current);

      if (!selectedFile) {
        pendingContentRef.current = '';
        setCurrentContent('');
        setActiveAnchor(null);
        setActiveLine(1);
        setRevisionStack([]);
        return;
      }

      const nextContent = selectedFile.content || '';
      pendingContentRef.current = nextContent;
      setCurrentContent(nextContent);
      setSaveStatus('idle');
      setIsDirty(false);
      setShowToolsMenu(false);
      setActiveAction('revise_selection');
      setSuggestedDiagnostic(null);
      setSuggestionSeed('');
      setRevisionStack([]);

      window.requestAnimationFrame(() => {
        if (isTexFile) {
          updateAnchorFromEditor('cursor-block');
        }
      });
    }, [isTexFile, selectedFile?.content, selectedFile?.path, updateAnchorFromEditor]);

    useEffect(() => {
      return () => {
        if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
        if (saveStatusTimerRef.current) clearTimeout(saveStatusTimerRef.current);
        if (aiSaveTimerRef.current) clearTimeout(aiSaveTimerRef.current);
        selectionDisposablesRef.current.forEach((disposable) => disposable.dispose());
      };
    }, []);

    useEffect(() => {
      if (!showToolsMenu) return;
      const handlePointerDown = (event: MouseEvent) => {
        if (!toolsMenuRef.current?.contains(event.target as Node)) {
          setShowToolsMenu(false);
        }
      };
      window.addEventListener('mousedown', handlePointerDown);
      return () => window.removeEventListener('mousedown', handlePointerDown);
    }, [showToolsMenu]);

    const handleMonacoMount: OnMount = useCallback(
      (editor, monaco) => {
        editorRef.current = editor;
        monacoRef.current = monaco;
        ensureLatexMonaco(monaco);

        selectionDisposablesRef.current.forEach((disposable) => disposable.dispose());
        selectionDisposablesRef.current = [
          editor.onDidChangeCursorSelection(() => {
            const selection = editor.getSelection();
            updateAnchorFromEditor(selection && !isRangeEmpty(selection) ? 'selection' : 'cursor-block');
          }),
          editor.onDidChangeCursorPosition((event) => {
            setActiveLine(event.position.lineNumber);
          }),
          editor.onDidChangeModelContent(() => {
            const selection = editor.getSelection();
            updateAnchorFromEditor(selection && !isRangeEmpty(selection) ? 'selection' : 'cursor-block');
          }),
          editor.onMouseDown((event) => {
            if (!event.target.position) return;
            const targetType = event.target.type;
            if (
              targetType !== monaco.editor.MouseTargetType.GUTTER_GLYPH_MARGIN &&
              targetType !== monaco.editor.MouseTargetType.GUTTER_LINE_NUMBERS
            ) {
              return;
            }
            const lineNumber = event.target.position.lineNumber;
            const diagnostic = diagnosticsByLine.get(lineNumber)?.[0];
            if (diagnostic) {
              openDiagnosticFix(diagnostic);
            }
          }),
        ];

        updateAnchorFromEditor('cursor-block');
      },
      [diagnosticsByLine, openDiagnosticFix, updateAnchorFromEditor]
    );

    useEffect(() => {
      if (!editorRef.current || !monacoRef.current || !isTexFile) return;
      const model = editorRef.current.getModel();
      if (!model) return;

      const decorations = lineDiagnostics
        .filter((diagnostic) => diagnostic.line && diagnostic.line <= model.getLineCount())
        .map((diagnostic) => {
          const lineNumber = diagnostic.line || 1;
          const isError = diagnostic.severity === 'error';
          const hoverText = `${
            diagnostic.severity === 'error' ? 'Error' : diagnostic.severity === 'warning' ? 'Warning' : 'Info'
          }: ${diagnostic.message}`;

          return {
            range: new monacoRef.current!.Range(
              lineNumber,
              1,
              lineNumber,
              model.getLineMaxColumn(lineNumber)
            ),
            options: {
              isWholeLine: true,
              className: isError
                ? diagnostic.firstFatal
                  ? 'fw-diagnostic-line-error fw-diagnostic-line-fatal'
                  : 'fw-diagnostic-line-error'
                : 'fw-diagnostic-line-warning',
              glyphMarginClassName: isError
                ? 'fw-diagnostic-glyph-error'
                : 'fw-diagnostic-glyph-warning',
              glyphMarginHoverMessage: [{ value: hoverText }],
              hoverMessage: [{ value: hoverText }],
            },
          };
        });

      decorationIdsRef.current = editorRef.current.deltaDecorations(
        decorationIdsRef.current,
        decorations
      );
    }, [isTexFile, lineDiagnostics]);

    useEffect(() => {
      if (!scrollToLine || !editorRef.current || !monacoRef.current || !isTexFile) return;
      const model = editorRef.current.getModel();
      if (!model) return;

      const lineNumber = Math.min(Math.max(scrollToLine, 1), model.getLineCount());
      const range = new monacoRef.current.Range(
        lineNumber,
        1,
        lineNumber,
        model.getLineMaxColumn(lineNumber)
      );

      editorRef.current.setPosition({ lineNumber, column: 1 });
      editorRef.current.setSelection(range);
      editorRef.current.revealLineInCenter(lineNumber);
      updateAnchorFromEditor('cursor-block', range);

      flashDecorationIdsRef.current = editorRef.current.deltaDecorations(
        flashDecorationIdsRef.current,
        [
          {
            range,
            options: {
              isWholeLine: true,
              className: 'fw-highlight-line',
            },
          },
        ]
      );

      const timer = setTimeout(() => {
        if (!editorRef.current) return;
        flashDecorationIdsRef.current = editorRef.current.deltaDecorations(
          flashDecorationIdsRef.current,
          []
        );
      }, 1800);

      return () => clearTimeout(timer);
    }, [isTexFile, scrollToLine, updateAnchorFromEditor]);

    useImperativeHandle(
      ref,
      () => ({
        getCurrentLine: () => {
          if (isTexFile) {
            return activeAnchor?.selection.activeLine || activeLine || 1;
          }
          if (!textareaRef.current) return 1;
          const value = textareaRef.current.value.slice(0, textareaRef.current.selectionStart);
          return value.split('\n').length;
        },
        getSelectedLineCount: () => {
          if (isTexFile) {
            if (!activeAnchor) return 1;
            return (
              activeAnchor.selection.endLineNumber -
              activeAnchor.selection.startLineNumber +
              1
            );
          }
          if (!textareaRef.current) return 1;
          const selected = textareaRef.current.value.slice(
            textareaRef.current.selectionStart,
            textareaRef.current.selectionEnd
          );
          return Math.max(selected.split('\n').length, 1);
        },
      }),
      [activeAnchor, activeLine, isTexFile]
    );

    if (!selectedFile) {
      return (
        <div className="flex h-full items-center justify-center bg-[#0A0A0A]">
          {selectedProject ? (
            <div className="text-center text-zinc-400">
              <FolderOpen size={44} className="mx-auto mb-4 text-zinc-600" />
              <p className="text-sm font-medium">Select a file to begin writing</p>
              <p className="mt-2 text-xs text-zinc-500">{selectedProject.project.name}</p>
            </div>
          ) : (
            <div className="text-center text-zinc-400">
              <FolderOpen size={44} className="mx-auto mb-4 text-zinc-600" />
              <p className="text-sm font-medium">Welcome to FastWrite</p>
              <p className="mt-2 text-xs text-zinc-500">Import or select a project to get started</p>
            </div>
          )}
        </div>
      );
    }

    return (
      <div className="flex h-full flex-col overflow-hidden bg-[#070707] text-white">
        <div className="border-b border-white/6 px-4 py-3">
          <div className="flex items-center justify-between gap-4">
            <div className="flex min-w-0 items-center gap-3">
              <div className="inline-flex min-w-0 items-center gap-2.5 rounded-[18px] border border-white/18 bg-white/[0.06] px-3.5 py-2.5 shadow-[0_10px_30px_rgba(0,0,0,0.28)]">
                <FileText size={14} className="shrink-0 text-zinc-300" />
                <span className="truncate text-[14px] font-semibold text-white">
                  {selectedFile.name}
                </span>
              </div>

              <div className="hidden items-center gap-2 md:flex">
                {saveIndicator}
                {activeAnchor && (
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[10px] font-medium text-zinc-300">
                    <History size={11} />
                    {activeAnchor.rangeLabel}
                  </span>
                )}
                {lineDiagnostics.length > 0 && (
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-red-400/15 bg-red-400/10 px-2.5 py-1 text-[10px] font-medium text-red-100">
                    <AlertTriangle size={11} />
                    {lineDiagnostics.length} diagnostics
                  </span>
                )}
              </div>
            </div>

            <div className="relative" ref={toolsMenuRef}>
              <button
                onClick={() => setShowToolsMenu((prev) => !prev)}
                className="inline-flex items-center gap-2 rounded-[16px] border border-cyan-400/20 bg-[#0D2248] px-3.5 py-2.5 text-[13px] font-semibold text-cyan-50 shadow-[0_12px_30px_rgba(8,33,80,0.55)] transition-transform hover:scale-[1.01]"
              >
                <Wrench size={15} />
                工具
                <ChevronDown size={13} />
              </button>

              {showToolsMenu && (
                <div className="absolute right-0 top-[calc(100%+12px)] z-30 w-[320px] overflow-hidden rounded-[22px] border border-white/10 bg-[#121212] p-2 shadow-[0_20px_60px_rgba(0,0,0,0.5)]">
                  <div className="px-3 pb-2 pt-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                    Writing Actions
                  </div>
                  <div className="space-y-1">
                    {(Object.keys(ACTION_META) as AIAction[]).map((action) => {
                      const disabled = action === 'related_work' && !projectConfig?.kbId;
                      return (
                        <button
                          key={action}
                          disabled={disabled}
                          onClick={() => {
                            setActiveAction(action);
                            if (action !== 'fix_compile_error') {
                              setSuggestedDiagnostic(null);
                              setSuggestionSeed('');
                            }
                            setShowToolsMenu(false);
                          }}
                          className="flex w-full items-start gap-3 rounded-2xl px-3 py-3 text-left transition-colors hover:bg-white/6 disabled:cursor-not-allowed disabled:opacity-40"
                        >
                          <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-white/10 bg-white/5">
                            {renderActionIcon(action)}
                          </div>
                          <div className="min-w-0">
                            <div className="flex items-center gap-2 text-sm font-medium text-white">
                              <span>{ACTION_META[action].label}</span>
                              {activeAction === action && (
                                <span className="rounded-full bg-cyan-400/15 px-2 py-0.5 text-[10px] uppercase tracking-wide text-cyan-100">
                                  Active
                                </span>
                              )}
                            </div>
                            <p className="mt-1 text-xs leading-5 text-zinc-400">
                              {ACTION_META[action].description}
                            </p>
                          </div>
                        </button>
                      );
                    })}
                  </div>

                  <div className="my-2 border-t border-white/8" />

                  <button
                    onClick={() => {
                      setShowBackupTimeline(true);
                      setShowToolsMenu(false);
                    }}
                    className="flex w-full items-center gap-3 rounded-2xl px-3 py-3 text-left text-sm text-zinc-200 transition-colors hover:bg-white/6"
                  >
                    <Clock size={15} className="text-zinc-400" />
                    Version History
                  </button>
                  <button
                    onClick={() => {
                      setShowLLMSettings(true);
                      setShowToolsMenu(false);
                    }}
                    className="flex w-full items-center gap-3 rounded-2xl px-3 py-3 text-left text-sm text-zinc-200 transition-colors hover:bg-white/6"
                  >
                    <Bot size={15} className="text-zinc-400" />
                    全局 AI 设置
                  </button>
                  <button
                    onClick={() => {
                      handleUndoLastKeep();
                      setShowToolsMenu(false);
                    }}
                    disabled={revisionStack.length === 0}
                    className="flex w-full items-center gap-3 rounded-2xl px-3 py-3 text-left text-sm text-zinc-200 transition-colors hover:bg-white/6 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <History size={15} className="text-zinc-400" />
                    Undo Keep
                  </button>
                </div>
              )}
            </div>
          </div>

          {projectDiagnostics.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {projectDiagnostics.slice(0, 4).map((diagnostic) => (
                <button
                  key={diagnostic.id}
                  onClick={() => openDiagnosticFix(diagnostic)}
                  className="inline-flex items-center gap-1.5 rounded-full border border-red-400/15 bg-red-400/10 px-2.5 py-1 text-[11px] font-medium text-red-100 transition-colors hover:bg-red-400/16"
                  title={diagnostic.message}
                >
                  <Zap size={11} />
                  <span className="max-w-[360px] truncate">{diagnostic.message}</span>
                </button>
              ))}
              {projectDiagnostics.length > 4 && (
                <span className="inline-flex items-center rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[11px] text-zinc-300">
                  +{projectDiagnostics.length - 4} more
                </span>
              )}
            </div>
          )}
        </div>

        <div className="flex-1 overflow-hidden px-4 pb-4 pt-3">
          {isTexFile ? (
            <div className="relative h-full overflow-hidden rounded-[30px] border border-white/7 bg-[#050505] shadow-[0_32px_90px_rgba(0,0,0,0.45)]">
              <Editor
                path={selectedFile.path}
                value={currentContent}
                language={FASTWRITE_LATEX_LANGUAGE}
                theme={FASTWRITE_LATEX_THEME}
                beforeMount={ensureLatexMonaco}
                onMount={handleMonacoMount}
                onChange={(value) => handleContentChange(value || '')}
                loading={
                  <div className="flex h-full items-center justify-center text-sm text-zinc-500">
                    Loading editor...
                  </div>
                }
                options={{
                  automaticLayout: true,
                  glyphMargin: true,
                  minimap: { enabled: false },
                  lineNumbers: 'on',
                  lineNumbersMinChars: 3,
                  fontFamily: "'SF Mono', 'JetBrains Mono', 'Fira Code', Monaco, Menlo, monospace",
                  fontSize: 14,
                  fontLigatures: true,
                  lineHeight: 28,
                  wordWrap: 'on',
                  wrappingIndent: 'indent',
                  smoothScrolling: true,
                  cursorSmoothCaretAnimation: 'on',
                  renderLineHighlight: 'line',
                  scrollBeyondLastLine: false,
                  overviewRulerBorder: false,
                  overviewRulerLanes: 0,
                  matchBrackets: 'always',
                  bracketPairColorization: { enabled: true },
                  guides: {
                    indentation: true,
                    bracketPairs: true,
                    highlightActiveIndentation: true,
                  },
                  padding: {
                    top: 28,
                    bottom: editorBottomInset,
                  },
                  scrollbar: {
                    verticalScrollbarSize: 10,
                    horizontalScrollbarSize: 10,
                    alwaysConsumeMouseWheel: false,
                  },
                  stickyScroll: {
                    enabled: false,
                  },
                }}
              />

              <TexAIDock
                projectId={selectedProject?.project.id || ''}
                projectKbId={projectConfig?.kbId}
                currentFilePath={selectedFile.path}
                activeAction={activeAction}
                anchor={activeAnchor}
                histories={aiHistories}
                onHistoryChange={setAiHistories}
                onApplySuggestion={handleApplySuggestion}
                canUndoLastKeep={revisionStack.length > 0}
                onUndoLastKeep={handleUndoLastKeep}
                suggestedDiagnostic={suggestedDiagnostic}
                suggestionSeed={suggestionSeed}
                onOverlayInsetChange={setEditorBottomInset}
              />
            </div>
          ) : (
            <div className="h-full overflow-hidden rounded-[26px] border border-white/7 bg-[#0B0B0B] shadow-[0_24px_60px_rgba(0,0,0,0.35)]">
              <div className="border-b border-white/6 px-5 py-3 text-xs text-zinc-500">
                Plain text editor
              </div>
              <textarea
                ref={textareaRef}
                value={currentContent}
                onChange={(event) => handleContentChange(event.target.value)}
                className="editor-textarea h-[calc(100%-45px)] w-full resize-none border-0 bg-transparent px-5 py-5 text-sm leading-7 text-zinc-100 outline-none"
              />
            </div>
          )}
        </div>

        {showBackupTimeline && selectedFile && selectedProject && (
          <BackupTimeline
            projectId={selectedProject.project.id}
            filePath={selectedFile.path}
            fileName={selectedFile.name}
            currentContent={currentContent}
            onClose={() => setShowBackupTimeline(false)}
            onRestore={(content) => {
              if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
              setCurrentContent(content);
              pendingContentRef.current = content;
              setShowBackupTimeline(false);
              void persistContent(content);
            }}
          />
        )}

        <LLMSettingsModal
          isOpen={showLLMSettings}
          onClose={() => setShowLLMSettings(false)}
        />
      </div>
    );
  }
);

MainEditor.displayName = 'MainEditor';

export default MainEditor;
