// Project Types
export interface Project {
  id: string;
  name: string;
  type: 'local' | 'github';
  localPath: string;
  createdAt: string;
  status: 'active' | 'archived';
  githubUrl?: string;
  githubBranch?: string;
}

export interface SelectedProject {
  project: Project;
  activeFileId?: string;
  config?: ProjectConfig;
  files?: FileNode[];
}

export type CompileMode = 'auto' | 'local' | 'browser-preview';
export type LatexEngine = 'auto' | 'pdflatex' | 'xelatex' | 'lualatex';
export type BibTool = 'auto' | 'bibtex' | 'biber';
export type CompileProvider = 'browser-preview' | 'local';
export type CompileCommandKind = 'latexmk' | 'direct-engine';

export interface ProjectConfig {
  projectId: string;
  sectionsDir: string;
  backupsDir: string;
  bibFiles: string[];
  mainFile?: string;
  compileMode?: CompileMode;
  preferredEngine?: LatexEngine;
  shellEscape?: 'auto' | boolean;
  bibTool?: BibTool;
  kbId?: string;
  compiler?: 'pdflatex' | 'xelatex' | 'lualatex' | 'browser-wasm';
}

export interface LatexToolCapability {
  available: boolean;
  path?: string;
}

export interface LatexCapabilities {
  local: {
    latexmk: LatexToolCapability;
    pdflatex: LatexToolCapability;
    xelatex: LatexToolCapability;
    lualatex: LatexToolCapability;
    bibtex: LatexToolCapability;
    biber: LatexToolCapability;
    makeindex: LatexToolCapability;
    makeglossaries: LatexToolCapability;
  };
  remote: {
    available: boolean;
  };
}

export interface LatexProfile {
  mainFile: string | null;
  mainFilePath: string | null;
  recommendedEngine: Exclude<LatexEngine, 'auto'>;
  effectiveEngine: Exclude<LatexEngine, 'auto'>;
  shellEscape: boolean;
  bibTool: BibTool;
  suitableForBrowserPreview: boolean;
  browserPreviewReasons: string[];
  triggers: string[];
  usedLatexmkRc: boolean;
}

// File Types
export interface FileNode {
  id: string;
  name: string;
  type: 'file' | 'folder';
  path: string;
  children?: FileNode[];
  content?: string;
  isLaTeX?: boolean;
}

export interface SelectedFile {
  id: string;
  name: string;
  path: string;
  content?: string;
}

export interface SectionNode {
  id: string;
  level: number;
  title: string;
  line: number;
  lineStart?: number;
  filePath?: string;
  parentId?: string;
  children?: SectionNode[];
}

// Editor Types
export type ViewMode = 'section' | 'paragraph' | 'sentence';
export type AIAction =
  | 'revise_selection'
  | 'proofread_section'
  | 'fix_compile_error'
  | 'generate_latex'
  | 'related_work';

export interface GlobalLLMConfig {
  provider: string;
  base_url: string;
  model: string;
  api_key: string;
}

export interface CompileDiagnostic {
  id: string;
  severity: 'error' | 'warning' | 'info';
  filePath?: string;
  line?: number;
  column?: number;
  message: string;
  raw: string;
  firstFatal?: boolean;
  category?: 'missing-package' | 'missing-font' | 'missing-tool' | 'engine-mismatch' | 'shell-escape-required' | 'tex-error' | 'warning';
  provider?: CompileProvider;
  packageName?: string;
  toolName?: string;
  suggestion?: string;
}

export interface EditorSelection {
  startLineNumber: number;
  startColumn: number;
  endLineNumber: number;
  endColumn: number;
  startOffset: number;
  endOffset: number;
  selectedText: string;
  activeLine: number;
}

export interface EditorAnchor {
  selection: EditorSelection;
  rangeLabel: string;
  source: 'selection' | 'cursor-block' | 'diagnostic';
}

export interface AISuggestionReference {
  source: string;
  page?: number;
  content?: string;
}

export interface AISuggestion {
  content: string;
  model: string;
  action: AIAction;
  explanation: string;
  references?: AISuggestionReference[];
  diffSummary?: {
    additions: number;
    deletions: number;
    modifications: number;
  };
}

export interface TextItem {
  id: string;
  content: string;
  type: 'paragraph' | 'section' | 'sentence';
  lineStart: number;
  status: 'unchanged' | 'modified' | 'saved';
  modifiedContent?: string;
  aiAction?: AIAction;
  aiTimestamp?: string;
  thoughts?: string;
  level?: number;
  children?: TextItem[];
}

// Diff Types
export interface DiffChange {
  type: 'addition' | 'deletion' | 'modification';
  original: string;
  modified: string;
  lineNumber?: number;
  explanation?: string;
}

export interface DiffResult {
  itemId: string;
  hasChanges: boolean;
  changes: DiffChange[];
  summary: {
    additions: number;
    deletions: number;
    modifications: number;
  };
}

export interface DocumentRevision {
  id: string;
  action: AIAction;
  previousContent: string;
  nextContent: string;
  anchor: EditorAnchor;
  createdAt: string;
}

export interface TexAIDockState {
  action: AIAction;
  prompt: string;
  isProcessing: boolean;
}

export interface Backup {
  id: string;
  filename: string;
  filePath?: string;
  timestamp: string;
  content: string;
}

// LLM Provider for multi-API management
export interface LLMProvider {
  id: string;
  name: string;
  baseUrl: string;
  apiKey: string;
  models: string[];
  selectedModel: string;
  isActive: boolean;
  createdAt: number;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system' | 'ai';
  content: string;
  timestamp: Date;
  model?: string;
  suggestion?: string;
}
