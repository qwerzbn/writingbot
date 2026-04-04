'use client';

import { useEffect, useRef, useState } from 'react';
import {
  Bold,
  Bot,
  BookOpen,
  Columns2,
  Edit3,
  Eye,
  FileText,
  Heading1,
  Italic,
  Link2,
  Loader2,
  Save,
  Sparkles,
  Tags,
  Wand2,
} from 'lucide-react';

import MarkdownRenderer from '@/components/MarkdownRenderer';
import TagInput from '@/components/notebook/TagInput';
import { Button } from '@/components/ui/button';
import type { NotebookEditorMode } from '@/lib/stores/notebook-workspace-ui-store';
import { type NotebookNoteDetail, updateNoteMeta } from '@/lib/notebook-api';

interface SaveOutcome {
  updated?: NotebookNoteDetail;
  conflict?: string;
  latest?: NotebookNoteDetail;
  error?: string;
}

interface WorkspaceEditorProps {
  note: NotebookNoteDetail;
  mode: NotebookEditorMode;
  onModeChange: (mode: NotebookEditorMode) => void;
  onSaveDraft: (
    noteId: string,
    payload: { title?: string; content?: string; tags?: string[]; expected_updated_at: string }
  ) => Promise<SaveOutcome>;
}

type AiAction = 'polish' | 'continue' | 'summarize' | 'suggest_tags' | 'custom' | null;

function sourceLabel(note: NotebookNoteDetail): string {
  const source = note.source || {};
  if (source.type === 'knowledge_base') {
    return `${source.file_name || source.file_id || '知识库文件'}${
      source.page !== undefined && source.page !== null ? ` · p.${source.page}` : ''
    }`;
  }
  if (source.type === 'research') return '研究结果';
  if (source.type === 'co_writer') return '协同写作';
  return '手动笔记';
}

export default function WorkspaceEditor({
  note,
  mode,
  onModeChange,
  onSaveDraft,
}: WorkspaceEditorProps) {
  const [title, setTitle] = useState(note.title);
  const [content, setContent] = useState(note.content);
  const [tags, setTags] = useState<string[]>(note.tags);
  const [saving, setSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [aiAction, setAiAction] = useState<AiAction>(null);
  const [aiError, setAiError] = useState<string | null>(null);

  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const activeNoteIdRef = useRef(note.id);
  const updatedAtRef = useRef(note.updated_at);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const saveVersionRef = useRef(0);
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const switched = activeNoteIdRef.current !== note.id;
    activeNoteIdRef.current = note.id;
    if (switched && saveTimerRef.current) {
      clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
      saveVersionRef.current += 1;
    }
    setTitle(note.title);
    setContent(note.content);
    setTags(note.tags);
    setHasChanges(false);
    setSaveMessage(null);
    setAiError(null);
    setAiAction(null);
    updatedAtRef.current = note.updated_at;
  }, [note]);

  useEffect(() => {
    return () => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      if (abortControllerRef.current) abortControllerRef.current.abort();
    };
  }, []);

  const scheduleSave = (nextTitle: string, nextContent: string, nextTags: string[]) => {
    setHasChanges(true);
    setSaveMessage(null);
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    const currentSaveVersion = ++saveVersionRef.current;
    saveTimerRef.current = setTimeout(async () => {
      setSaving(true);
      const result = await onSaveDraft(note.id, {
        title: nextTitle,
        content: nextContent,
        tags: nextTags,
        expected_updated_at: updatedAtRef.current,
      });
      if (currentSaveVersion !== saveVersionRef.current) return;
      if (result.updated) {
        updatedAtRef.current = result.updated.updated_at;
        setHasChanges(false);
        setSaveMessage('已保存');
      } else if (result.latest) {
        updatedAtRef.current = result.latest.updated_at;
        setTitle(result.latest.title);
        setContent(result.latest.content);
        setTags(result.latest.tags);
        setHasChanges(false);
        setSaveMessage(result.conflict || '检测到冲突，已同步最新内容');
      } else {
        setHasChanges(true);
        setSaveMessage(result.conflict || result.error || '保存失败');
      }
      setSaving(false);
    }, 900);
  };

  const handleTitleChange = (value: string) => {
    setTitle(value);
    scheduleSave(value, content, tags);
  };

  const handleContentChange = (value: string) => {
    setContent(value);
    scheduleSave(title, value, tags);
  };

  const handleTagsChange = (nextTags: string[]) => {
    setTags(nextTags);
    scheduleSave(title, content, nextTags);
  };

  const insertAtCursor = (before: string, after = '') => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const selected = content.slice(start, end);
    const next = `${content.slice(0, start)}${before}${selected}${after}${content.slice(end)}`;
    handleContentChange(next);
    window.setTimeout(() => {
      textarea.focus();
      textarea.selectionStart = start + before.length;
      textarea.selectionEnd = start + before.length + selected.length;
    }, 0);
  };

  const persistMeta = async (payload: { summary?: string; suggested_tags?: string[] }) => {
    try {
      await updateNoteMeta(note.notebook_id, note.id, payload);
    } catch {
      // Keep editor responsive even if meta persistence fails.
    }
  };

  const handleAiAction = async (
    action: Exclude<AiAction, null>,
    instruction = '',
    options?: { writeToContent?: boolean }
  ) => {
    const writeToContent = options?.writeToContent ?? true;
    if (!content.trim() && action !== 'continue' && action !== 'custom') {
      setAiError('当前笔记为空，请先输入内容。');
      return;
    }

    if (abortControllerRef.current) abortControllerRef.current.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setAiError(null);
    setAiAction(action);

    let buffered = '';
    let nextContent = content;
    if (action === 'polish') nextContent = '';
    if (action === 'continue') nextContent = `${content}\n\n`;
    if (action === 'summarize' && writeToContent) nextContent = `> **AI 摘要**：\n> `;
    if (action === 'custom') nextContent = `${content}\n\n---\n\n### AI 工作台\n`;

    try {
      const response = await fetch('/api/notebooks/ai/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action,
          content: action === 'continue' ? content.slice(-2400) : content,
          title,
          instruction,
        }),
        signal: controller.signal,
      });
      if (!response.ok) {
        throw new Error(`AI 请求失败 (${response.status})`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('AI 响应为空');
      const decoder = new TextDecoder();
      let buffer = '';

      const applyChunk = (chunkPayload: string) => {
        if (!chunkPayload || chunkPayload === '[DONE]') return;
        const parsed = JSON.parse(chunkPayload) as { chunk?: string; error?: string };
        if (parsed.error) throw new Error(parsed.error);
        if (!parsed.chunk) return;
        buffered += parsed.chunk;
        if (!writeToContent) return;
        if (action === 'polish') setContent(buffered);
        if (action === 'continue') setContent(nextContent + buffered);
        if (action === 'summarize') {
          const summaryLines = buffered
            .split('\n')
            .map((line) => `> ${line}`)
            .join('\n');
          setContent(`> **AI 摘要**：\n${summaryLines}\n\n${content}`);
        }
        if (action === 'custom') setContent(nextContent + buffered);
      };

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split('\n\n');
        buffer = events.pop() || '';
        for (const event of events) {
          for (const line of event.split('\n')) {
            if (line.startsWith('data:')) {
              applyChunk(line.slice(5).trim());
            }
          }
        }
      }

      if (action === 'suggest_tags') {
        const nextTags = Array.from(
          new Set(
            buffered
              .replace(/[\[\]"]/g, '')
              .split(',')
              .map((item) => item.trim())
              .filter(Boolean)
              .concat(tags)
          )
        ).slice(0, 10);
        setTags(nextTags);
        scheduleSave(title, content, nextTags);
        await persistMeta({ suggested_tags: nextTags });
      } else if (writeToContent) {
        let finalContent = content;
        if (action === 'polish') finalContent = buffered;
        if (action === 'continue') finalContent = nextContent + buffered;
        if (action === 'summarize') {
          const summaryLines = buffered
            .split('\n')
            .map((line) => `> ${line}`)
            .join('\n');
          finalContent = `> **AI 摘要**：\n${summaryLines}\n\n${content}`;
          await persistMeta({ summary: buffered.trim() });
        }
        if (action === 'custom') finalContent = nextContent + buffered;
        setContent(finalContent);
        scheduleSave(title, finalContent, tags);
      } else if (action === 'summarize') {
        await persistMeta({ summary: buffered.trim() });
      }
    } catch (error) {
      if (!(error instanceof Error && error.name === 'AbortError')) {
        setAiError(error instanceof Error ? error.message : 'AI 执行失败');
      }
    } finally {
      if (abortControllerRef.current === controller) {
        abortControllerRef.current = null;
      }
      setAiAction(null);
    }
  };

  const stopAi = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setAiAction(null);
  };

  const toolbarItems = [
    { label: '粗体', icon: Bold, action: () => insertAtCursor('**', '**') },
    { label: '斜体', icon: Italic, action: () => insertAtCursor('*', '*') },
    { label: '标题', icon: Heading1, action: () => insertAtCursor('## ') },
    { label: '链接', icon: Link2, action: () => insertAtCursor('[', '](url)') },
  ];
  const noteSummary = note.ai_meta?.summary?.trim() || '把这条卡片扩展成一段可以继续写作的研究线索。';

  return (
    <div className="notebook-sheen animate-notebook-rise flex h-full min-h-0 flex-col rounded-[1.75rem] border border-stone-200/80 bg-[linear-gradient(180deg,rgba(251,248,243,0.96),rgba(242,233,220,0.98))] text-stone-900 shadow-[0_24px_90px_-54px_rgba(41,37,36,0.45)]">
      <div className="border-b border-stone-200/80 bg-[radial-gradient(circle_at_top_left,rgba(14,116,144,0.08),transparent_30%),linear-gradient(180deg,rgba(255,255,255,0.72),rgba(255,255,255,0.42))] px-6 pb-4 pt-6">
        <div className="space-y-4">
          <div className="min-w-0">
            <textarea
              value={title}
              onChange={(event) => handleTitleChange(event.target.value)}
              placeholder="给这条笔记起一个清晰的标题"
              rows={2}
              className="min-h-[4.4rem] w-full resize-none bg-transparent font-serif text-[clamp(1.8rem,3vw,2.8rem)] font-semibold leading-[1.05] tracking-tight text-stone-900 outline-none placeholder:text-stone-400"
            />
            <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-stone-500">
              <span className="inline-flex items-center gap-1 rounded-full border border-stone-200 bg-white/78 px-3 py-1">
                <BookOpen className="h-3.5 w-3.5" />
                {sourceLabel(note)}
              </span>
              <span>更新于 {new Date(note.updated_at).toLocaleString('zh-CN')}</span>
              <span className="inline-flex items-center gap-1">
                <Save className={`h-3.5 w-3.5 ${saving ? 'animate-pulse text-amber-600' : 'text-emerald-700'}`} />
                {saving ? '自动保存中' : hasChanges ? '等待保存' : '已同步'}
              </span>
            </div>

            <div className="mt-4 rounded-[1.35rem] border border-stone-200/70 bg-white/72 px-4 py-3 shadow-[0_10px_35px_-30px_rgba(41,37,36,0.65)]">
              <div className="text-[11px] font-medium uppercase tracking-[0.22em] text-stone-400">Current Angle</div>
              <p className="mt-2 text-sm leading-6 text-stone-600">{noteSummary}</p>
            </div>
          </div>

          <div className="flex justify-end">
            <div className="inline-flex rounded-full border border-stone-200 bg-white/92 p-1 shadow-sm">
              {[
                { key: 'edit' as const, label: '编辑', icon: Edit3 },
                { key: 'split' as const, label: '分屏', icon: Columns2 },
                { key: 'preview' as const, label: '预览', icon: Eye },
              ].map(({ key, label, icon: Icon }) => (
                <button
                  key={key}
                  onClick={() => onModeChange(key)}
                  className={`inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium transition ${
                    mode === key ? 'bg-stone-900 text-stone-50' : 'text-stone-500 hover:text-stone-900'
                  }`}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {label}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="mt-4">
          <TagInput
            tags={tags}
            onChange={handleTagsChange}
            placeholder="添加标签，回车确认"
          />
        </div>

        {saveMessage ? (
          <div className="mt-3 rounded-2xl border border-stone-200 bg-white/80 px-3 py-2 text-xs text-stone-600">
            {saveMessage}
          </div>
        ) : null}
      </div>

      <div className="border-b border-stone-200/80 bg-[linear-gradient(180deg,rgba(237,228,216,0.95),rgba(234,222,207,0.85))] px-5 py-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-1">
            {toolbarItems.map(({ label, icon: Icon, action }) => (
              <button
                key={label}
                onClick={action}
                disabled={mode === 'preview' || Boolean(aiAction)}
                title={label}
                className="rounded-full p-2 text-stone-500 transition hover:bg-white hover:text-stone-900 disabled:cursor-not-allowed disabled:opacity-40"
              >
                <Icon className="h-4 w-4" />
              </button>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-2 rounded-full bg-stone-900 px-3 py-1 text-xs font-medium text-stone-50">
              <Bot className={`h-3.5 w-3.5 ${aiAction ? 'animate-pulse' : ''}`} />
              AI 命令
            </span>
            {aiAction ? (
              <Button variant="outline" size="sm" onClick={stopAi} className="rounded-full bg-white/80">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                停止
              </Button>
            ) : null}
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="outline"
            className="rounded-full bg-white/85"
            disabled={Boolean(aiAction) || !content.trim()}
            onClick={() => void handleAiAction('polish')}
          >
            <Sparkles className="h-3.5 w-3.5" />
            润色全文
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="rounded-full bg-white/85"
            disabled={Boolean(aiAction)}
            onClick={() => void handleAiAction('continue')}
          >
            <Edit3 className="h-3.5 w-3.5" />
            AI 续写
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="rounded-full bg-white/85"
            disabled={Boolean(aiAction) || !content.trim()}
            onClick={() => void handleAiAction('summarize')}
          >
            <FileText className="h-3.5 w-3.5" />
            生成摘要
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="rounded-full bg-white/85"
            disabled={Boolean(aiAction) || !content.trim()}
            onClick={() => void handleAiAction('suggest_tags')}
          >
            <Tags className="h-3.5 w-3.5" />
            推荐标签
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="rounded-full bg-white/85"
            disabled={Boolean(aiAction)}
            onClick={() =>
              void handleAiAction(
                'custom',
                '请把当前内容整理成一张研究阅读卡，按“问题 / 方法 / 发现 / 局限 / 下一步”五节输出。'
              )
            }
          >
            <Wand2 className="h-3.5 w-3.5" />
            重组卡片
          </Button>
        </div>

        {aiError ? <div className="mt-3 text-xs text-red-600">{aiError}</div> : null}
      </div>

      <div className="flex min-h-0 flex-1">
        {(mode === 'edit' || mode === 'split') && (
          <div
            className={`min-h-0 flex-1 ${mode === 'split' ? 'border-r border-stone-200/80' : ''}`}
          >
            <textarea
              ref={textareaRef}
              value={content}
              onChange={(event) => handleContentChange(event.target.value)}
              disabled={Boolean(aiAction)}
              placeholder="用 Markdown 记录问题、方法、证据与下一步。"
              className="h-full min-h-[26rem] w-full resize-none bg-[linear-gradient(180deg,rgba(255,255,255,0.42),rgba(255,255,255,0.18))] px-6 py-6 font-mono text-sm leading-7 text-stone-800 outline-none placeholder:text-stone-400 disabled:opacity-70"
            />
          </div>
        )}

        {(mode === 'preview' || mode === 'split') && (
          <div className="min-h-0 flex-1 overflow-auto bg-[linear-gradient(180deg,rgba(255,255,255,0.42),rgba(247,241,232,0.82))] px-6 py-6">
            {content.trim() ? (
              <MarkdownRenderer content={content} />
            ) : (
              <div className="flex h-full min-h-[26rem] flex-col items-center justify-center text-stone-400">
                <BookOpen className="mb-3 h-8 w-8" />
                <p className="text-sm">开始写作后，这里会出现排版预览。</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
