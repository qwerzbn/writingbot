'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Search, Loader2, Send, FileText, BookOpen, BadgeCheck, Download } from 'lucide-react';

import { useAppContext } from '@/context/AppContext';
import MarkdownRenderer from '@/components/MarkdownRenderer';

interface NotebookOption {
  id: string;
  name: string;
}

interface ResearchMeta {
  paper_hits: number;
  citation_coverage: number;
  inference_ratio: number;
}

const DEFAULT_META: ResearchMeta = {
  paper_hits: 0,
  citation_coverage: 0,
  inference_ratio: 0,
};

function toPercent(value: number): string {
  return `${Math.round((value || 0) * 100)}%`;
}

function sanitizePdfText(input: string): string {
  return (input || '')
    .replace(/[^\x20-\x7E\n]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function escapePdfText(input: string): string {
  return input.replace(/\\/g, '\\\\').replace(/\(/g, '\\(').replace(/\)/g, '\\)');
}

function wrapText(input: string, width = 86): string[] {
  const text = sanitizePdfText(input);
  if (!text) return [];
  const words = text.split(' ');
  const lines: string[] = [];
  let current = '';
  for (const word of words) {
    if (!word) continue;
    const candidate = current ? `${current} ${word}` : word;
    if (candidate.length <= width) {
      current = candidate;
      continue;
    }
    if (current) lines.push(current);
    current = word.slice(0, width);
  }
  if (current) lines.push(current);
  return lines;
}

function buildSimplePdf(lines: string[]): Blob {
  const textLines = lines.slice(0, 52);
  const streamLines = [
    'BT',
    '/F1 11 Tf',
    '40 800 Td',
    '14 TL',
    ...textLines.map((line) => `(${escapePdfText(line)}) Tj T*`),
    'ET',
  ];
  const stream = streamLines.join('\n');

  const objects = [
    '1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj',
    '2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj',
    '3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >> endobj',
    `4 0 obj << /Length ${stream.length} >> stream\n${stream}\nendstream endobj`,
    '5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj',
  ];

  let pdf = '%PDF-1.4\n';
  const offsets: number[] = [0];
  for (const obj of objects) {
    offsets.push(pdf.length);
    pdf += `${obj}\n`;
  }
  const xrefStart = pdf.length;
  pdf += `xref\n0 ${objects.length + 1}\n`;
  pdf += '0000000000 65535 f \n';
  for (let i = 1; i <= objects.length; i += 1) {
    pdf += `${String(offsets[i]).padStart(10, '0')} 00000 n \n`;
  }
  pdf += `trailer << /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefStart}\n%%EOF`;
  return new Blob([new TextEncoder().encode(pdf)], { type: 'application/pdf' });
}

export default function ResearchPage() {
  const { kbs, selectedKbId, setSelectedKbId } = useAppContext();

  const [topic, setTopic] = useState('');
  const [plan, setPlan] = useState('');
  const [report, setReport] = useState('');
  const [sources, setSources] = useState<Array<Record<string, unknown>>>([]);
  const [meta, setMeta] = useState<ResearchMeta>(DEFAULT_META);
  const [loading, setLoading] = useState(false);

  const [notebooks, setNotebooks] = useState<NotebookOption[]>([]);
  const [saveNotebookId, setSaveNotebookId] = useState('');
  const [savingNote, setSavingNote] = useState(false);

  useEffect(() => {
    const loadNotebooks = async () => {
      try {
        const res = await fetch('/api/notebooks');
        const data = await res.json();
        if (!data.success) return;
        const rows = (data.data || []) as NotebookOption[];
        setNotebooks(rows);
        if (!saveNotebookId && rows.length > 0) {
          setSaveNotebookId(rows[0].id);
        }
      } catch {
        setNotebooks([]);
      }
    };
    void loadNotebooks();
  }, [saveNotebookId]);

  const metrics = useMemo(
    () => [
      { label: 'Paper Hits', value: String(meta.paper_hits || 0) },
      { label: 'Citation Coverage', value: toPercent(meta.citation_coverage || 0) },
      { label: 'Inference Ratio', value: toPercent(meta.inference_ratio || 0) },
    ],
    [meta]
  );

  const handleResearch = useCallback(async () => {
    if (!topic.trim() || loading) return;

    setLoading(true);
    setPlan('');
    setReport('');
    setSources([]);
    setMeta(DEFAULT_META);

    try {
      const res = await fetch('/api/research/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          topic: topic.trim(),
          kb_id: selectedKbId || undefined,
        }),
      });

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) return;

      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const data = JSON.parse(line.slice(6));
            if (data.type === 'plan') {
              setPlan(String(data.content || ''));
            } else if (data.type === 'chunk') {
              setReport((prev) => prev + String(data.content || ''));
            } else if (data.type === 'sources') {
              setSources((data.data || []) as Array<Record<string, unknown>>);
              if (data.meta) {
                setMeta((prev) => ({
                  paper_hits: Number(data.meta.paper_hits ?? prev.paper_hits ?? 0),
                  citation_coverage: Number(data.meta.citation_coverage ?? prev.citation_coverage ?? 0),
                  inference_ratio: Number(data.meta.inference_ratio ?? prev.inference_ratio ?? 0),
                }));
              }
            } else if (data.type === 'done') {
              const m = data.meta || {};
              setMeta({
                paper_hits: Number(m.paper_hits || 0),
                citation_coverage: Number(m.citation_coverage || 0),
                inference_ratio: Number(m.inference_ratio || 0),
              });
            }
          } catch {
            // Ignore malformed chunks.
          }
        }
      }
    } catch {
      setReport('Research report generation failed. Please retry.');
    } finally {
      setLoading(false);
    }
  }, [loading, selectedKbId, topic]);

  const saveReportToNotebook = async () => {
    if (!saveNotebookId || !report.trim() || savingNote) return;
    setSavingNote(true);
    try {
      const title = topic.trim() ? `研究笔记：${topic.trim().slice(0, 48)}` : '研究笔记';
      await fetch(`/api/notebooks/${saveNotebookId}/notes/from-sources`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title,
          content: report,
          sources,
          kb_id: selectedKbId || undefined,
          origin_type: 'research',
          tags: ['research'],
        }),
      });
    } finally {
      setSavingNote(false);
    }
  };

  const exportResearchCardPdf = () => {
    const now = new Date().toISOString().replace('T', ' ').slice(0, 19);
    const lines: string[] = [
      'WritingBot Research Process Card',
      `Generated At: ${now}`,
      `Topic: ${sanitizePdfText(topic) || 'N/A'}`,
      `Paper Hits: ${meta.paper_hits || 0}`,
      `Citation Coverage: ${toPercent(meta.citation_coverage || 0)}`,
      `Inference Ratio: ${toPercent(meta.inference_ratio || 0)}`,
      '',
      'Plan:',
      ...wrapText(plan || 'N/A'),
      '',
      'Report Excerpt:',
      ...wrapText((report || '').slice(0, 2200)),
      '',
      `Sources: ${sources.length}`,
    ];

    const blob = buildSimplePdf(lines);
    const filenameTopic = sanitizePdfText(topic).replace(/\s+/g, '_').slice(0, 40) || 'research';
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `research-card-${filenameTopic}.pdf`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="min-h-screen bg-slate-50 p-8 transition-colors dark:bg-slate-900">
      <div className="mx-auto max-w-4xl">
        <div className="mb-8">
          <h1 className="mb-2 flex items-center gap-3 text-2xl font-bold text-slate-800 dark:text-white">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-emerald-500 to-teal-400 text-white shadow-lg">
              <Search size={20} />
            </div>
            深度研究
          </h1>
          <p className="text-slate-500 dark:text-slate-400">输入研究主题，生成可追溯的研究过程与报告。</p>
        </div>

        <div className="mb-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-800">
          <div className="mb-4 flex gap-3">
            <select
              value={selectedKbId || ''}
              onChange={(e) => setSelectedKbId(e.target.value || null)}
              className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-200"
            >
              <option value="">不使用知识库</option>
              {kbs.map((kb) => (
                <option key={kb.id} value={kb.id}>
                  {kb.name}
                </option>
              ))}
            </select>
            <select
              value={saveNotebookId}
              onChange={(e) => setSaveNotebookId(e.target.value)}
              className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-200"
            >
              <option value="">不保存到笔记本</option>
              {notebooks.map((nb) => (
                <option key={nb.id} value={nb.id}>
                  {nb.name}
                </option>
              ))}
            </select>
          </div>
          <div className="flex gap-3">
            <input
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && void handleResearch()}
              placeholder="输入研究主题，例如：Transformer 在 NLP 中的应用"
              className="flex-1 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 dark:border-slate-600 dark:bg-slate-700 dark:text-white"
            />
            <button
              onClick={() => void handleResearch()}
              disabled={loading || !topic.trim()}
              className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-emerald-500 to-teal-500 px-6 py-3 font-medium text-white transition-all hover:from-emerald-600 hover:to-teal-600 disabled:opacity-50"
              type="button"
            >
              {loading ? <Loader2 size={18} className="animate-spin" /> : <Send size={18} />}
              生成报告
            </button>
          </div>
        </div>

        {(report || plan) && (
          <div className="mb-6 rounded-xl border border-emerald-200 bg-emerald-50 p-4 dark:border-emerald-800 dark:bg-emerald-900/20">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-emerald-700 dark:text-emerald-300">
              <BadgeCheck size={16} />
              证据可信度面板
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              {metrics.map((item) => (
                <div key={item.label} className="rounded-lg border border-emerald-200/80 bg-white/80 px-3 py-2 dark:border-emerald-800 dark:bg-slate-900/30">
                  <div className="text-xs text-slate-500 dark:text-slate-400">{item.label}</div>
                  <div className="text-lg font-semibold text-slate-800 dark:text-white">{item.value}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {plan && (
          <div className="mb-6 rounded-xl border border-emerald-200 bg-emerald-50 p-5 dark:border-emerald-800 dark:bg-emerald-900/20">
            <h3 className="mb-2 text-sm font-semibold text-emerald-700 dark:text-emerald-400">研究计划</h3>
            <MarkdownRenderer content={plan} />
          </div>
        )}

        {report && (
          <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-800">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-600 dark:text-slate-300">
                <FileText size={16} /> 研究报告
              </h3>
              <div className="flex items-center gap-2">
                <button
                  onClick={exportResearchCardPdf}
                  className="inline-flex items-center gap-1.5 rounded-md bg-emerald-100 px-3 py-1.5 text-xs text-emerald-700 hover:bg-emerald-200 dark:bg-emerald-900/40 dark:text-emerald-200 dark:hover:bg-emerald-900/60"
                  type="button"
                >
                  <Download size={12} />
                  导出研究过程卡片(PDF)
                </button>
                <button
                  onClick={saveReportToNotebook}
                  disabled={!saveNotebookId || savingNote}
                  className="inline-flex items-center gap-1.5 rounded-md bg-slate-100 px-3 py-1.5 text-xs hover:bg-slate-200 disabled:opacity-50 dark:bg-slate-700 dark:hover:bg-slate-600"
                  type="button"
                >
                  {savingNote ? <Loader2 size={12} className="animate-spin" /> : <BookOpen size={12} />}
                  保存为笔记
                </button>
              </div>
            </div>
            <MarkdownRenderer content={report} />
          </div>
        )}

        {loading && !report && (
          <div className="py-16 text-center text-slate-400">
            <Loader2 size={32} className="mx-auto mb-4 animate-spin" />
            <p>正在进行深度研究...</p>
          </div>
        )}
      </div>
    </div>
  );
}
