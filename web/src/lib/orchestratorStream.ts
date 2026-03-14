import type { OrchestratorDoneEvent, OrchestratorEvent, OrchestratorMode, OrchestratorRunDetail } from '@/types/orchestrator';

interface RunOrchestratorOptions {
  mode: OrchestratorMode;
  payload: Record<string, unknown>;
  onEvent: (event: OrchestratorEvent) => void;
  signal?: AbortSignal;
  apiBase?: string;
}

interface RunOrchestratorResult {
  runId: string;
  traceId?: string;
  doneEvent?: OrchestratorDoneEvent;
  runDetail?: OrchestratorRunDetail;
}

export async function getOrchestratorRunDetail(runId: string, apiBase = ''): Promise<OrchestratorRunDetail> {
  const res = await fetch(`${apiBase}/api/orchestrator/run/${runId}`, {
    method: 'GET',
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(txt || `Run detail failed (${res.status})`);
  }
  const body = await res.json();
  return body?.data as OrchestratorRunDetail;
}

export async function runOrchestratorStream(options: RunOrchestratorOptions): Promise<RunOrchestratorResult> {
  const base = options.apiBase ?? '';
  const runRes = await fetch(`${base}/api/orchestrator/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode: options.mode, payload: options.payload }),
    signal: options.signal,
  });

  if (!runRes.ok) {
    const txt = await runRes.text();
    throw new Error(txt || `Run create failed (${runRes.status})`);
  }

  const runBody = await runRes.json();
  const runId = runBody?.data?.run_id as string;
  const traceId = runBody?.data?.trace_id as string | undefined;
  if (!runId) {
    throw new Error('Missing run_id from orchestrator');
  }

  const streamRes = await fetch(`${base}/api/orchestrator/stream/${runId}`, {
    method: 'GET',
    signal: options.signal,
  });
  if (!streamRes.ok) {
    const txt = await streamRes.text();
    throw new Error(txt || `Stream failed (${streamRes.status})`);
  }

  const reader = streamRes.body?.getReader();
  if (!reader) {
    throw new Error('No stream body');
  }

  const decoder = new TextDecoder();
  let buffer = '';
  let sawTerminal = false;
  let doneEvent: OrchestratorDoneEvent | undefined;

  const splitConcatenatedJsonObjects = (raw: string): string[] => {
    const chunks: string[] = [];
    let depth = 0;
    let inString = false;
    let escape = false;
    let start = -1;

    for (let i = 0; i < raw.length; i += 1) {
      const ch = raw[i];
      if (inString) {
        if (escape) {
          escape = false;
        } else if (ch === '\\') {
          escape = true;
        } else if (ch === '"') {
          inString = false;
        }
        continue;
      }
      if (ch === '"') {
        inString = true;
        continue;
      }
      if (ch === '{') {
        if (depth === 0) start = i;
        depth += 1;
        continue;
      }
      if (ch === '}') {
        if (depth === 0) continue;
        depth -= 1;
        if (depth === 0 && start >= 0) {
          chunks.push(raw.slice(start, i + 1));
          start = -1;
        }
      }
    }
    return chunks;
  };

  const emitRawEvent = (raw: string): boolean => {
    const trimmed = raw.trim();
    if (!trimmed) return true;
    try {
      const event = JSON.parse(trimmed) as OrchestratorEvent;
      if (event.type === 'done') {
        sawTerminal = true;
        doneEvent = event;
      } else if (event.type === 'error') {
        sawTerminal = true;
      }
      options.onEvent(event);
      return true;
    } catch {
      return false;
    }
  };

  const dispatchBlock = (block: string) => {
    if (!block.trim()) return;
    const dataLines: string[] = [];
    for (const line of block.split(/\r?\n/)) {
      if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).trimStart());
      }
    }
    if (!dataLines.length) return;

    const raw = dataLines.join('\n').trim();
    if (emitRawEvent(raw)) return;

    const chunks = splitConcatenatedJsonObjects(raw);
    if (!chunks.length) {
      console.warn('orchestrator stream parse skipped invalid payload:', raw.slice(0, 300));
      return;
    }
    for (const chunk of chunks) {
      if (!emitRawEvent(chunk)) {
        console.warn('orchestrator stream parse skipped invalid chunk:', chunk.slice(0, 300));
      }
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split(/\r?\n\r?\n/);
    buffer = events.pop() || '';

    for (const event of events) {
      dispatchBlock(event);
    }
  }

  if (buffer.trim()) {
    dispatchBlock(buffer);
  }

  if (!sawTerminal) {
    const detail = await getOrchestratorRunDetail(runId, base);
    if (detail.status === 'done') {
      const recoveredDone: OrchestratorDoneEvent = {
        type: 'done',
        run_id: detail.run_id,
        trace_id: detail.trace_id,
        output: detail.result?.output,
        sources: detail.result?.sources,
        metrics: detail.metrics,
      };
      options.onEvent(recoveredDone);
      return { runId, traceId, doneEvent: recoveredDone, runDetail: detail };
    }
    if (detail.status === 'failed') {
      throw new Error(String(detail.result?.error || 'stream closed before completion'));
    }
    throw new Error('stream closed before terminal event');
  }

  const detail = await getOrchestratorRunDetail(runId, base);
  return { runId, traceId, doneEvent, runDetail: detail };
}
