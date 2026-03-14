export type OrchestratorMode = 'research' | 'writing' | 'chat_research';

export interface OrchestratorRunMetrics {
  stage_timings_ms?: Partial<Record<'plan' | 'retrieve' | 'synthesize' | 'critique' | 'finalize', number>>;
  attempts?: Partial<Record<'plan' | 'retrieve' | 'synthesize' | 'critique' | 'finalize', number>>;
  retry_count?: number;
  retry_rate?: number;
  failure_count?: number;
  failure_rate?: number;
  empty_evidence_rate?: number;
  citation_missing_fix?: number;
  source_count?: number;
  evidence_status?: 'unknown' | 'ok' | 'no_kb' | 'kb_unavailable' | 'no_match' | 'filtered_out';
  citation_coverage?: number;
  paper_hit_rate?: number;
  skill_success_rate?: number;
  inference_ratio?: number;
  model_calls?: Array<{
    stage?: string;
    provider?: string;
    model?: string;
    prompt_tokens?: number;
    completion_tokens?: number;
    estimated_usd?: number;
  }>;
  model_cost?: {
    provider?: string;
    model?: string;
    calls?: number;
    prompt_tokens?: number;
    completion_tokens?: number;
    estimated_usd?: number;
  };
}

export interface OrchestratorBaseEvent {
  type: 'init' | 'step' | 'chunk' | 'sources' | 'metric' | 'error' | 'done';
  timestamp?: string;
  trace_id?: string;
  run_id?: string;
}

export interface OrchestratorInitEvent extends OrchestratorBaseEvent {
  type: 'init';
  mode?: OrchestratorMode;
}

export interface OrchestratorStepEvent extends OrchestratorBaseEvent {
  type: 'step';
  step: 'plan' | 'retrieve' | 'synthesize' | 'critique' | 'finalize';
  status: 'working' | 'done' | 'retry' | 'skipped' | 'error';
  attempt?: number;
  message?: string;
  duration_ms?: number;
  confidence?: number;
  agent_id?: string;
}

export interface OrchestratorChunkEvent extends OrchestratorBaseEvent {
  type: 'chunk';
  content: string;
}

export interface OrchestratorSourcesEvent extends OrchestratorBaseEvent {
  type: 'sources';
  data: Array<{
    id?: string;
    source: string;
    page: number | string;
    file_id?: string;
    content?: string;
    score?: number;
    relevance?: number;
    factual_risk?: number;
  }>;
}

export interface OrchestratorMetricEvent extends OrchestratorBaseEvent {
  type: 'metric';
  name: string;
  value: number;
  unit?: string;
}

export interface OrchestratorErrorEvent extends OrchestratorBaseEvent {
  type: 'error';
  error: string;
  step?: string;
  retryable?: boolean;
}

export interface OrchestratorDoneEvent extends OrchestratorBaseEvent {
  type: 'done';
  output?: string;
  sources?: OrchestratorSourcesEvent['data'];
  total_ms?: number;
  plan?: string;
  metrics?: OrchestratorRunMetrics;
  meta?: {
    selected_skill_ids?: string[];
    skill_runs?: Array<{
      skill_id: string;
      status: string;
      critical?: boolean;
      error?: string;
      duration_ms?: number;
    }>;
    paper_hits?: number;
  };
}

export interface OrchestratorRunDetail {
  run_id: string;
  trace_id: string;
  mode: OrchestratorMode;
  status: string;
  created_at: string;
  expires_at: string;
  result?: {
    output?: string;
    sources?: OrchestratorSourcesEvent['data'];
    metrics?: OrchestratorRunMetrics;
    error?: string;
    [key: string]: unknown;
  };
  metrics?: OrchestratorRunMetrics;
}

export type OrchestratorEvent =
  | OrchestratorInitEvent
  | OrchestratorStepEvent
  | OrchestratorChunkEvent
  | OrchestratorSourcesEvent
  | OrchestratorMetricEvent
  | OrchestratorErrorEvent
  | OrchestratorDoneEvent;
