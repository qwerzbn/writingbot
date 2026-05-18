import OpenAI from 'openai';
import { existsSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';

import type {
  AIAction,
  AISuggestion,
  AISuggestionReference,
  CompileDiagnostic,
} from '../web/src/types';
import { fetchGlobalLLMConfig, getWritingBotBaseUrl } from './writingbotSettings';

const PROJS_DIR = join(process.cwd(), 'projs');
const LLM_CONFIG_FILE = join(PROJS_DIR, 'llm-config.json');
const LLM_PROVIDERS_FILE = join(PROJS_DIR, 'llm-providers.json');

export interface LLMConfig {
  baseUrl: string;
  apiKey: string;
  model: string;
}

// New: LLM Provider for multi-API management
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

// Load config from file, fallback to environment variables
export function getLLMConfig(): LLMConfig {
  // First try to get from active provider
  const providers = getLLMProviders();
  const activeProvider = providers.find(p => p.isActive);
  if (activeProvider) {
    return {
      baseUrl: activeProvider.baseUrl,
      apiKey: activeProvider.apiKey,
      model: activeProvider.selectedModel
    };
  }

  // Fallback to legacy config file
  try {
    if (existsSync(LLM_CONFIG_FILE)) {
      const data = JSON.parse(readFileSync(LLM_CONFIG_FILE, 'utf-8'));
      return {
        baseUrl: data.baseUrl || process.env.OPENAI_BASE_URL || 'https://api.openai.com/v1',
        apiKey: data.apiKey || process.env.OPENAI_API_KEY || '',
        model: data.model || process.env.OPENAI_MODEL || 'gpt-4o'
      };
    }
  } catch (error) {
    console.error('Failed to load LLM config:', error);
  }

  return {
    baseUrl: process.env.OPENAI_BASE_URL || 'https://api.openai.com/v1',
    apiKey: process.env.OPENAI_API_KEY || '',
    model: process.env.OPENAI_MODEL || 'gpt-4o'
  };
}

// Save config to file (legacy, for backward compatibility)
export function saveLLMConfig(config: Partial<LLMConfig>): boolean {
  try {
    if (!existsSync(PROJS_DIR)) {
      mkdirSync(PROJS_DIR, { recursive: true });
    }

    const currentConfig = getLLMConfig();
    const newConfig = {
      baseUrl: config.baseUrl ?? currentConfig.baseUrl,
      apiKey: config.apiKey ?? currentConfig.apiKey,
      model: config.model ?? currentConfig.model
    };

    writeFileSync(LLM_CONFIG_FILE, JSON.stringify(newConfig, null, 2), 'utf-8');
    console.log(`Synced LLM config to ${LLM_CONFIG_FILE}: model=${newConfig.model}`);
    return true;
  } catch (error) {
    console.error('Failed to save LLM config:', error);
    return false;
  }
}

// ============ LLM Provider Management ============

// Load all providers
export function getLLMProviders(): LLMProvider[] {
  try {
    if (existsSync(LLM_PROVIDERS_FILE)) {
      const data = JSON.parse(readFileSync(LLM_PROVIDERS_FILE, 'utf-8'));
      return Array.isArray(data) ? data : [];
    }
  } catch (error) {
    console.error('Failed to load LLM providers:', error);
  }
  return [];
}

// Save all providers
function saveLLMProviders(providers: LLMProvider[]): boolean {
  try {
    if (!existsSync(PROJS_DIR)) {
      mkdirSync(PROJS_DIR, { recursive: true });
    }
    writeFileSync(LLM_PROVIDERS_FILE, JSON.stringify(providers, null, 2), 'utf-8');

    // Also sync the active provider to the legacy config file
    const activeProvider = providers.find(p => p.isActive);
    if (activeProvider) {
      saveLLMConfig({
        baseUrl: activeProvider.baseUrl,
        apiKey: activeProvider.apiKey, // Note: This might save masked key if not careful, but source is unmasked from getLLMProviders
        model: activeProvider.selectedModel
      });
    }

    return true;
  } catch (error) {
    console.error('Failed to save LLM providers:', error);
    return false;
  }
}

// Add or update a provider
export function saveLLMProvider(provider: LLMProvider): boolean {
  const providers = getLLMProviders();
  const existingIndex = providers.findIndex(p => p.id === provider.id);

  if (existingIndex >= 0) {
    // Check if API key is masked and restore original if so
    const existing = providers[existingIndex];
    if (existing && provider.apiKey && provider.apiKey.includes('...') && existing.apiKey) {
      const prefix = existing.apiKey.substring(0, 8);
      const suffix = existing.apiKey.substring(existing.apiKey.length - 4);
      const masked = `${prefix}...${suffix}`;

      // If the provided key matches the masked pattern of the existing key, keep the existing key
      if (provider.apiKey === masked) {
        console.log(`Restoring original API key for provider ${provider.name}`);
        provider.apiKey = existing.apiKey;
      }
    }
    if (existing) {
      providers[existingIndex] = provider;
    }
  } else {
    providers.push(provider);
  }

  return saveLLMProviders(providers);
}

// Delete a provider
export function deleteLLMProvider(id: string): boolean {
  const providers = getLLMProviders();
  const filtered = providers.filter(p => p.id !== id);

  // If deleted provider was active, activate another one
  if (filtered.length > 0 && !filtered.some(p => p.isActive) && filtered[0]) {
    filtered[0].isActive = true;
  }

  return saveLLMProviders(filtered);
}

// Set active provider
export function setActiveProvider(id: string): boolean {
  const providers = getLLMProviders();
  let found = false;

  for (const provider of providers) {
    if (provider.id === id) {
      provider.isActive = true;
      found = true;
    } else {
      provider.isActive = false;
    }
  }

  if (!found) return false;
  return saveLLMProviders(providers);
}

// Fetch models from OpenAI-compatible API
export async function fetchModelsFromAPI(baseUrl: string, apiKey: string): Promise<string[]> {
  try {
    const normalizedUrl = baseUrl.replace(/\/+$/, '').replace(/\/chat\/completions\/?$/, '');
    const client = new OpenAI({
      apiKey,
      baseURL: normalizedUrl,
      timeout: 10000
    });

    const response = await client.models.list();
    const models: string[] = [];

    for await (const model of response) {
      models.push(model.id);
    }

    // Sort models alphabetically
    return models.sort((a, b) => a.localeCompare(b));
  } catch (error) {
    console.error('Failed to fetch models:', error);
    throw error;
  }
}

export type AIMode = 'diagnose' | 'refine' | 'quickfix';

export interface AIRequest {
  action?: AIAction;
  mode?: AIMode;
  content: string;
  systemPrompt?: string;
  userPrompt?: string;
  history?: { role: 'user' | 'ai'; content: string }[];
  projectId?: string;
  filePath?: string;
  targetItemId?: string;
  lineStart?: number;
  lineEnd?: number;
  contextScope?: 'selection' | 'section' | 'document';
  diagnostic?: CompileDiagnostic | null;
  kbId?: string;
}

export interface ProjectAIContext {
  selection: string;
  currentSection?: string;
  previousBlock?: string;
  nextBlock?: string;
  outline: string[];
  diagnostics: CompileDiagnostic[];
  references: AISuggestionReference[];
}

const DEFAULT_PROMPTS: Record<AIMode, { system: string; user: string }> = {
  diagnose: {
    system: `You are an expert academic writing reviewer for top-tier computer science conferences (IEEE S&P, USENIX Security, OSDI, CCS).

Your goal is to analyze and discuss the paper's structure, logic flow, and argumentation.

Provide constructive feedback on:
1. Logical flow and argumentation structure
2. Whether the problem statement clearly articulates tensions or trade-offs
3. Clarity of the main contributions
4. Any structural issues or missing elements

Be specific and constructive. Point out both strengths and areas for improvement.`,
    user: 'Please analyze and diagnose the following text. Discuss the structure, logic flow, and identify any issues with clarity or argumentation. Provide specific and constructive feedback.'
  },
  refine: {
    system: `You are a strict and professional academic editor for top-tier computer security and systems conferences (IEEE S&P, USENIX Security, OSDI, CCS). Your goal is to refine the text to meet high publication standards.

**Task:** Rewrite and polish the text to make it **concise, precise, and authoritative**.

**Style Guidelines (Strictly Follow):**

1. **Conciseness & High Information Density:**
   - Eliminate all filler words and redundant adjectives (remove "very," "extremely," "successfully")
   - Every sentence must convey new information
   - Use **Active Voice** (e.g., "The system validates" not "The data is validated by")

2. **Authoritative & Direct Tone:**
   - Use strong, specific verbs (enforce, guarantee, mitigate, isolate, decouple, orchestrate)
   - Avoid hedging (no "we try to," "it seems that"). Be confident: "We demonstrate," "We present"
   - When describing your work, use "We + Verb"

3. **Logical Flow & Signposting:**
   - Use logical connectors: In contrast, Conversely, Consequently, Specifically, To address this...
   - Ensure problem statements show clear **tension** or **trade-off**

4. **Terminological Precision:**
   - Use technical terms consistently
   - Distinguish between actors (Attacker vs. User vs. Developer)
   - Avoid vague pronouns - repeat nouns when ambiguous

5. **Quantitative over Qualitative:**
   - Prefer "reduces overhead by 5x" over "greatly reduces"
   - Prefer "negligible impact (<1%)" over "very fast"

Return ONLY the refined text without any explanations.`,
    user: 'Please refine the following text. Improve clarity, structure, eliminate redundancy, and enhance academic writing quality. Return only the refined text.'
  },
  quickfix: {
    system: `You are a grammar and style checker for academic writing.
Fix ONLY:
- Grammar errors
- Spelling mistakes
- Punctuation issues
- Syntax errors

Do NOT:
- Change the meaning or structure
- Rephrase sentences
- Add or remove content
- Modify technical terms

Return only the corrected text with minimal changes.`,
    user: 'Please fix any grammar, spelling, punctuation, or syntax errors in the following text. Do not change the meaning or structure. Return only the corrected text.'
  }
};

// Export for use by API endpoints
export { DEFAULT_PROMPTS };

type ActionPrompt = { user: string };

// Project-specific prompts type - shared system + action-specific user prompts
export interface ProjectPrompts {
  system: string;
  revise_selection: ActionPrompt;
  proofread_section: ActionPrompt;
  fix_compile_error: ActionPrompt;
  generate_latex: ActionPrompt;
  related_work: ActionPrompt;
}

// Default shared system prompt
const DEFAULT_SHARED_SYSTEM = `**System Role:**
You are a strict and professional academic editor and reviewer for top-tier computer security and systems conferences (such as IEEE S&P, USENIX Security, OSDI, CCS). Your goal is to refine the user's draft to meet the high standards of these venues, specifically mimicking the writing style of high-quality systems papers (e.g., the "bpftime" OSDI'25 paper).

**Task:**
Rewrite and polish the provided text. The goal is to make it **concise, precise, and authoritative**.

**Style Guidelines (Strictly Follow These):**

1. **Conciseness & Density (High Information Density):**
    - Eliminate all "fluff," filler words, and redundant adjectives (e.g., remove "very," "extremely," "successfully").
    - Every sentence must convey new information or a necessary logical step.
    - Avoid long-winded passive constructions. Use **Active Voice** whenever possible (e.g., Change "The data is validated by the system" to "The system validates the data").

2. **Authoritative & Direct Tone:**
    - Use strong, specific verbs (e.g., _enforce, guarantee, mitigate, isolate, decouple, orchestrate_).
    - Avoid hedging or weak language (e.g., avoid "we try to," "it seems that"). Be confident in the contributions (e.g., "We demonstrate," "We present").
    - When describing your own work, use "We + Verb" (e.g., "We introduce EIM...").

3. **Logical Flow & Signposting:**
    - Use logical connectors to guide the reader's thinking, similar to a mathematical proof.
    - Use phrases like: _In contrast, Conversely, Consequently, Specifically, To address this challenge, On the one hand... On the other hand..._
    - Ensure the problem statement clearly articulates the **tension** or **trade-off** (e.g., "Safety vs. Efficiency").

4. **Terminological Precision:**
    - Ensure technical terms are used consistently.
    - Distinguish clearly between actors (e.g., "Attacker" vs. "User" vs. "Developer").
    - Avoid vague pronouns. If "it" is ambiguous, repeat the noun.

5. **Quantitative over Qualitative:**
    - Prefer "reduces overhead by 5x" over "greatly reduces overhead."
    - Prefer "negligible performance impact (<1%)" over "very fast."

**Example of Style Transformation:**

- _Bad (Draft):_ "We made a new system called X that is very good at stopping attacks. It is better than Y because Y is slow. X uses a cool technique to check memory."
- _Good (Target Style):_ "We present X, a system that enforces memory safety with negligible overhead. Unlike Y, which relies on slow context switches, X employs lightweight in-process isolation to mitigate attacks efficiently."`;

const ACTION_DEFAULTS: Record<AIAction, { label: string; user: string; system: string; temperature: number }> = {
  revise_selection: {
    label: 'Revise Selection',
    user: 'Revise the selected text. Improve clarity, technical precision, and flow while preserving LaTeX syntax.',
    system: 'Return only the revised LaTeX/text for the selected target. Do not add commentary or code fences.',
    temperature: 0.3,
  },
  proofread_section: {
    label: 'Proofread Section',
    user: 'Proofread the selected section. Fix grammar, phrasing, and readability while preserving meaning and structure.',
    system: 'Return only the corrected LaTeX/text. Keep the original structure and LaTeX commands intact.',
    temperature: 0.15,
  },
  fix_compile_error: {
    label: 'Fix Compile Error',
    user: 'Fix the compile issue with the smallest valid LaTeX change. Prioritize successful compilation over stylistic edits.',
    system: 'Return only the corrected LaTeX/text needed to fix the compile issue.',
    temperature: 0.1,
  },
  generate_latex: {
    label: 'Generate LaTeX',
    user: 'Generate a polished LaTeX draft for the selected location using the surrounding project context.',
    system: 'Return only valid LaTeX/text that can be inserted directly into the document.',
    temperature: 0.35,
  },
  related_work: {
    label: 'Related Work',
    user: 'Rewrite the selected text into a related-work style paragraph grounded in the supplied evidence.',
    system: 'Return only the rewritten LaTeX/text. Do not invent citations or unsupported claims.',
    temperature: 0.25,
  },
};

export const DEFAULT_PROJECT_PROMPTS: ProjectPrompts = {
  system: DEFAULT_SHARED_SYSTEM,
  revise_selection: { user: ACTION_DEFAULTS.revise_selection.user },
  proofread_section: { user: ACTION_DEFAULTS.proofread_section.user },
  fix_compile_error: { user: ACTION_DEFAULTS.fix_compile_error.user },
  generate_latex: { user: ACTION_DEFAULTS.generate_latex.user },
  related_work: { user: ACTION_DEFAULTS.related_work.user },
};

function resolveProjectPrompt(data: Record<string, any>, action: AIAction): ActionPrompt {
  const directPrompt = data?.[action]?.user;
  if (typeof directPrompt === 'string' && directPrompt.trim()) {
    return { user: directPrompt };
  }

  const legacyPrompt = {
    revise_selection: data?.refine?.user,
    proofread_section: data?.proofread_section?.user || data?.quickfix?.user || data?.diagnose?.user,
    fix_compile_error: data?.fix_compile_error?.user,
    generate_latex: data?.generate_latex?.user,
    related_work: data?.related_work?.user,
  }[action];

  if (typeof legacyPrompt === 'string' && legacyPrompt.trim()) {
    return { user: legacyPrompt };
  }

  return DEFAULT_PROJECT_PROMPTS[action];
}

// Get project prompts (returns project-specific or defaults)
export function getProjectPrompts(projectId: string): ProjectPrompts {
  const promptsFile = join(PROJS_DIR, projectId, 'prompts.json');

  try {
    if (existsSync(promptsFile)) {
      const data = JSON.parse(readFileSync(promptsFile, 'utf-8')) as Record<string, any>;
      return {
        system: data.system || DEFAULT_SHARED_SYSTEM,
        revise_selection: resolveProjectPrompt(data, 'revise_selection'),
        proofread_section: resolveProjectPrompt(data, 'proofread_section'),
        fix_compile_error: resolveProjectPrompt(data, 'fix_compile_error'),
        generate_latex: resolveProjectPrompt(data, 'generate_latex'),
        related_work: resolveProjectPrompt(data, 'related_work'),
      };
    }
  } catch (error) {
    console.error('Failed to load project prompts:', error);
  }

  return DEFAULT_PROJECT_PROMPTS;
}

// Save project prompts
export function saveProjectPrompts(projectId: string, prompts: Partial<ProjectPrompts>): boolean {
  const projectDir = join(PROJS_DIR, projectId);
  const promptsFile = join(projectDir, 'prompts.json');

  try {
    if (!existsSync(projectDir)) {
      mkdirSync(projectDir, { recursive: true });
    }

    const current = getProjectPrompts(projectId);
    const merged: ProjectPrompts = {
      system: prompts.system ?? current.system,
      revise_selection: { user: prompts.revise_selection?.user ?? current.revise_selection.user },
      proofread_section: { user: prompts.proofread_section?.user ?? current.proofread_section.user },
      fix_compile_error: { user: prompts.fix_compile_error?.user ?? current.fix_compile_error.user },
      generate_latex: { user: prompts.generate_latex?.user ?? current.generate_latex.user },
      related_work: { user: prompts.related_work?.user ?? current.related_work.user },
    };

    writeFileSync(promptsFile, JSON.stringify(merged, null, 2), 'utf-8');
    return true;
  } catch (error) {
    console.error('Failed to save project prompts:', error);
    return false;
  }
}

// Export default shared system prompt for reset
export { DEFAULT_SHARED_SYSTEM };

function resolveAction(request: AIRequest): AIAction {
  if (request.action) return request.action;
  switch (request.mode) {
    case 'diagnose':
      return 'proofread_section';
    case 'quickfix':
      return 'fix_compile_error';
    case 'refine':
    default:
      return 'revise_selection';
  }
}

function stripMarkdownCodeFences(text: string): string {
  const trimmed = text.trim();
  const match = trimmed.match(/^\s*```[\w-]*\s*\n([\s\S]*?)\n```\s*$/);
  return (match?.[1] ?? trimmed).trim();
}

function tokenize(text: string): string[] {
  return text.split(/\s+/).map((item) => item.trim()).filter(Boolean);
}

function summarizeDiff(original: string, revised: string) {
  const originalWords = tokenize(original);
  const revisedWords = tokenize(revised);
  if (original === revised) {
    return { additions: 0, deletions: 0, modifications: 0 };
  }
  return {
    additions: Math.max(revisedWords.length - originalWords.length, 0),
    deletions: Math.max(originalWords.length - revisedWords.length, 0),
    modifications: 1,
  };
}

function extractOutline(lines: string[]): string[] {
  const sectionRegex = /\\(section|subsection|subsubsection)\*?\s*\{([^}]*)\}/;
  return lines
    .map((line, index) => {
      const match = line.match(sectionRegex);
      if (!match) return null;
      const level = match[1] === 'section' ? '#' : match[1] === 'subsection' ? '##' : '###';
      return `${level} ${(match[2] || '').trim()} (line ${index + 1})`;
    })
    .filter((item): item is string => Boolean(item))
    .slice(0, 24);
}

function findCurrentSection(lines: string[], lineStart?: number): string | undefined {
  if (!lineStart) return undefined;
  const sectionRegex = /\\(section|subsection|subsubsection)\*?\s*\{([^}]*)\}/;

  for (let idx = Math.min(lineStart - 1, lines.length - 1); idx >= 0; idx--) {
    const match = lines[idx]?.match(sectionRegex);
    if (match) {
      return `${match[1]}: ${(match[2] || '').trim()}`;
    }
  }
  return undefined;
}

function buildContextWindow(lines: string[], lineStart?: number, lineEnd?: number) {
  if (!lineStart) return { previousBlock: undefined, nextBlock: undefined };
  const start = Math.max(0, lineStart - 1);
  const end = Math.min(lines.length - 1, (lineEnd || lineStart) - 1);
  return {
    previousBlock: lines.slice(Math.max(0, start - 8), start).join('\n').trim() || undefined,
    nextBlock: lines.slice(end + 1, Math.min(lines.length, end + 9)).join('\n').trim() || undefined,
  };
}

async function fetchEvidenceReferences(request: AIRequest, action: AIAction): Promise<AISuggestionReference[]> {
  if (!request.kbId || action !== 'related_work') {
    return [];
  }

  try {
    const response = await fetch(`${getWritingBotBaseUrl()}/api/co-writer/evidence`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: request.userPrompt?.trim() || request.content.slice(0, 1200),
        kb_id: request.kbId,
        top_k: 4,
      }),
    });

    if (!response.ok) return [];
    const payload = await response.json() as { success?: boolean; data?: AISuggestionReference[] };
    return payload.success && payload.data ? payload.data : [];
  } catch (error) {
    console.warn('Failed to fetch WritingBot evidence:', error);
    return [];
  }
}

async function buildProjectAIContext(request: AIRequest, action: AIAction): Promise<ProjectAIContext> {
  const context: ProjectAIContext = {
    selection: request.content,
    outline: [],
    diagnostics: request.diagnostic ? [request.diagnostic] : [],
    references: await fetchEvidenceReferences(request, action),
  };

  if (request.filePath && existsSync(request.filePath)) {
    const fileContent = readFileSync(request.filePath, 'utf-8');
    const lines = fileContent.split('\n');
    context.outline = extractOutline(lines);
    context.currentSection = findCurrentSection(lines, request.lineStart);
    const nearby = buildContextWindow(lines, request.lineStart, request.lineEnd);
    context.previousBlock = nearby.previousBlock;
    context.nextBlock = nearby.nextBlock;
  }

  return context;
}

function buildUserMessage(request: AIRequest, action: AIAction, context: ProjectAIContext): string {
  const prompt = ACTION_DEFAULTS[action];
  const segments = [
    `Action: ${prompt.label}`,
    '',
    prompt.user,
  ];

  if (request.userPrompt?.trim()) {
    segments.push('', `Additional instruction: ${request.userPrompt.trim()}`);
  }

  segments.push('', 'Selected target:', request.content.trim());

  if (context.currentSection) {
    segments.push('', `Current section: ${context.currentSection}`);
  }
  if (context.previousBlock) {
    segments.push('', 'Previous context:', context.previousBlock);
  }
  if (context.nextBlock) {
    segments.push('', 'Next context:', context.nextBlock);
  }
  if (context.outline.length > 0) {
    segments.push('', 'Document outline:', context.outline.join('\n'));
  }
  if (context.diagnostics.length > 0) {
    segments.push(
      '',
      'Compile diagnostics:',
      context.diagnostics
        .map((diag) => `${diag.severity.toUpperCase()}: ${diag.message}${diag.line ? ` (line ${diag.line})` : ''}`)
        .join('\n')
    );
  }
  if (context.references.length > 0) {
    segments.push(
      '',
      'Evidence references:',
      context.references
        .map((ref, index) => `[${index + 1}] ${ref.source}${ref.page ? ` p.${ref.page}` : ''}: ${(ref.content || '').trim()}`)
        .join('\n')
    );
  }

  return segments.join('\n');
}

function buildSuggestionExplanation(action: AIAction, referenceCount: number): string {
  const base = {
    revise_selection: 'Prepared a revision using the surrounding project context.',
    proofread_section: 'Prepared a proofread pass that keeps the original intent intact.',
    fix_compile_error: 'Prepared the smallest compile-oriented fix justified by the diagnostics.',
    generate_latex: 'Prepared a new LaTeX draft aligned with the surrounding structure.',
    related_work: 'Prepared a related-work style revision grounded in the available evidence.',
  }[action];

  if (referenceCount === 0) return base;
  return `${base} Included ${referenceCount} supporting reference${referenceCount > 1 ? 's' : ''}.`;
}

export async function processWithAI(request: AIRequest): Promise<AISuggestion> {
  const action = resolveAction(request);
  const config = await fetchGlobalLLMConfig();

  if (!config.api_key) {
    throw new Error('WritingBot global AI setting is missing an API key. Open the main app settings and save a valid model configuration.');
  }

  const client = new OpenAI({
    apiKey: config.api_key,
    baseURL: config.base_url.replace(/\/chat\/completions\/?$/, ''),
    timeout: 30000,
  });

  const context = await buildProjectAIContext(request, action);
  const historyMessages = (request.history || []).map((message) => ({
    role: message.role === 'ai' ? 'assistant' : 'user',
    content: message.content,
  })) as OpenAI.Chat.Completions.ChatCompletionMessageParam[];

  const systemPrompt = [
    request.systemPrompt || DEFAULT_SHARED_SYSTEM,
    ACTION_DEFAULTS[action].system,
  ].join('\n\n');

  try {
    const response = await client.chat.completions.create({
      model: config.model,
      messages: [
        { role: 'system', content: systemPrompt },
        ...historyMessages,
        { role: 'user', content: buildUserMessage(request, action, context) },
      ],
      temperature: ACTION_DEFAULTS[action].temperature,
      max_tokens: 4000,
    });

    const content = response.choices[0]?.message?.content;
    if (!content) {
      throw new Error('AI API returned empty content');
    }

    const cleaned = stripMarkdownCodeFences(content);
    return {
      content: cleaned,
      model: config.model,
      action,
      explanation: buildSuggestionExplanation(action, context.references.length),
      references: context.references,
      diffSummary: summarizeDiff(request.content, cleaned),
    };
  } catch (error) {
    if (error instanceof OpenAI.APIError) {
      throw new Error(`API error ${error.status}: ${error.message}`);
    }
    throw error;
  }
}

export async function loadAICache(projectPath: string): Promise<Record<string, any[]>> {
  try {
    const cachePath = join(projectPath, '.fastwrite', 'ai-cache.json');
    if (!existsSync(cachePath)) return {};
    const content = await Bun.file(cachePath).text();
    return JSON.parse(content);
  } catch (error) {
    console.error('Failed to load AI cache:', error);
    return {};
  }
}

export async function saveAICache(projectPath: string, cache: Record<string, any[]>) {
  try {
    const dir = join(projectPath, '.fastwrite');
    if (!existsSync(dir)) {
      mkdirSync(dir, { recursive: true });
    }
    const cachePath = join(projectPath, '.fastwrite', 'ai-cache.json');
    await Bun.write(cachePath, JSON.stringify(cache, null, 2));
  } catch (e) {
    console.error('Failed to save AI cache:', e);
  }
}
