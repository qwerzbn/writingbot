'use client';

import type { OrchestratorRunMetrics } from '@/types/orchestrator';
import { ChevronDown, ChevronUp, Activity } from 'lucide-react';

interface RunDiagnosticsProps {
  title?: string;
  runId?: string | null;
  traceId?: string | null;
  currentStep?: string | null;
  status?: string | null;
  totalMs?: number | null;
  metrics?: OrchestratorRunMetrics | null;
  collapsed?: boolean;
  onToggle?: () => void;
}

function evidenceStatusLabel(status?: string) {
  switch (status) {
    case 'ok':
      return '证据正常';
    case 'no_kb':
      return '未使用知识库';
    case 'kb_unavailable':
      return '知识库不可用';
    case 'no_match':
      return '检索为空';
    case 'filtered_out':
      return '证据被过滤';
    default:
      return '未知';
  }
}

export default function RunDiagnostics({
  title = '运行诊断',
  runId,
  traceId,
  currentStep,
  status,
  totalMs,
  metrics,
  collapsed = true,
  onToggle,
}: RunDiagnosticsProps) {
  const sourceCount = metrics?.source_count ?? 0;
  const retryCount = metrics?.retry_count ?? 0;
  const failureCount = metrics?.failure_count ?? 0;
  const emptyEvidenceRate = metrics?.empty_evidence_rate ?? 0;
  const modelCost = metrics?.model_cost?.estimated_usd ?? 0;

  return (
    <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-3 text-left"
      >
        <div className="flex items-center gap-2">
          <Activity size={15} className="text-slate-500 dark:text-slate-400" />
          <div>
            <div className="text-sm font-medium text-slate-700 dark:text-slate-200">{title}</div>
            <div className="text-xs text-slate-500 dark:text-slate-400">
              {status || 'idle'}{currentStep ? ` · ${currentStep}` : ''}
            </div>
          </div>
        </div>
        {collapsed ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
      </button>

      {!collapsed && (
        <div className="px-4 pb-4 grid grid-cols-1 md:grid-cols-2 gap-3 text-xs text-slate-600 dark:text-slate-300">
          <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/40 p-3 space-y-1">
            <div>run_id：{runId || '-'}</div>
            <div>trace_id：{traceId || '-'}</div>
            <div>当前阶段：{currentStep || '-'}</div>
            <div>总耗时：{typeof totalMs === 'number' ? `${totalMs} ms` : '-'}</div>
          </div>
          <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/40 p-3 space-y-1">
            <div>证据状态：{evidenceStatusLabel(metrics?.evidence_status)}</div>
            <div>sources：{sourceCount}</div>
            <div>retry：{retryCount}</div>
            <div>failure：{failureCount}</div>
            <div>empty evidence：{(emptyEvidenceRate * 100).toFixed(0)}%</div>
            <div>model cost：${modelCost.toFixed(6)}</div>
          </div>
        </div>
      )}
    </div>
  );
}
