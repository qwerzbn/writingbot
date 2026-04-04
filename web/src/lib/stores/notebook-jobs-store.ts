import { create } from 'zustand';

import type { NotebookEvent, NotebookJob } from '@/lib/notebook-api';

type StreamStatus = 'idle' | 'connecting' | 'open' | 'error';

interface NotebookJobsState {
  jobsByNotebook: Record<string, NotebookJob[]>;
  latestCompletedJobByNotebook: Record<string, NotebookJob | null>;
  streamStatusByNotebook: Record<string, StreamStatus>;
  seedJobs: (notebookId: string, jobs: NotebookJob[]) => void;
  upsertJob: (notebookId: string, job: NotebookJob) => void;
  applyEvent: (notebookId: string, event: NotebookEvent) => void;
  setLatestCompletedJob: (notebookId: string, job: NotebookJob | null) => void;
  setStreamStatus: (notebookId: string, status: StreamStatus) => void;
}

function normalizeJob(existing: NotebookJob | undefined, event: NotebookEvent): NotebookJob {
  return {
    id: event.job_id || existing?.id || '',
    job_type: event.job_type || existing?.job_type || 'unknown',
    status: (event.status as NotebookJob['status']) || existing?.status || 'pending',
    progress: event.progress ?? existing?.progress ?? 0,
    processed: event.processed ?? existing?.processed,
    total: event.total ?? existing?.total,
    message: event.message ?? existing?.message,
    note_ids: event.affected_note_ids ?? existing?.note_ids,
    updated_at: event.timestamp ?? existing?.updated_at,
  };
}

export const useNotebookJobsStore = create<NotebookJobsState>((set) => ({
  jobsByNotebook: {},
  latestCompletedJobByNotebook: {},
  streamStatusByNotebook: {},
  seedJobs: (notebookId, jobs) =>
    set((state) => ({
      jobsByNotebook: { ...state.jobsByNotebook, [notebookId]: jobs },
    })),
  upsertJob: (notebookId, job) =>
    set((state) => {
      const existing = state.jobsByNotebook[notebookId] ?? [];
      const matchIndex = existing.findIndex((item) => item.id === job.id);
      const next =
        matchIndex >= 0
          ? existing.map((item, index) => (index === matchIndex ? { ...item, ...job } : item))
          : [job, ...existing];
      return {
        jobsByNotebook: { ...state.jobsByNotebook, [notebookId]: next },
      };
    }),
  applyEvent: (notebookId, event) =>
    set((state) => {
      if (!event.job_id) return state;
      const existing = state.jobsByNotebook[notebookId] ?? [];
      const match = existing.find((item) => item.id === event.job_id);
      const nextJob = normalizeJob(match, event);
      const nextJobs =
        nextJob.status === 'pending' || nextJob.status === 'running'
          ? match
            ? existing.map((item) => (item.id === event.job_id ? nextJob : item))
            : [nextJob, ...existing]
          : existing.filter((item) => item.id !== event.job_id);
      return {
        jobsByNotebook: { ...state.jobsByNotebook, [notebookId]: nextJobs },
        latestCompletedJobByNotebook:
          nextJob.status === 'done' || nextJob.status === 'partial_failed' || nextJob.status === 'error'
            ? { ...state.latestCompletedJobByNotebook, [notebookId]: nextJob }
            : state.latestCompletedJobByNotebook,
      };
    }),
  setLatestCompletedJob: (notebookId, job) =>
    set((state) => ({
      latestCompletedJobByNotebook: {
        ...state.latestCompletedJobByNotebook,
        [notebookId]: job,
      },
    })),
  setStreamStatus: (notebookId, status) =>
    set((state) => ({
      streamStatusByNotebook: { ...state.streamStatusByNotebook, [notebookId]: status },
    })),
}));
