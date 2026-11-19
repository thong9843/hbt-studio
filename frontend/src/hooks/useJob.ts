import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api/endpoints';
import type { Job } from '../api/types';

export interface JobProgress {
  progress: number;
  step: string;
  message: string;
  stage?: string;
  current?: number;
  total?: number;
  current_beat?: number | null;
  total_beats?: number | null;
  percent?: number;
  text?: string;
}

const EMPTY: JobProgress = { progress: 0, step: '', message: '' };

/**
 * Theo dõi một job dựng video qua SSE (`/api/jobs/{id}/events`). Khi có sự kiện `end` (hoặc mất kết
 * nối) thì đọc lại `GET /jobs/{id}` để có URL file đầu ra.
 */
export function useJob(
  jobId: string | null,
  onFinished?: (job: Job) => void,
  seedProgress?: Partial<JobProgress> | null,
) {
  const [progress, setProgress] = useState<JobProgress>(EMPTY);
  const [job, setJob] = useState<Job | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const finishedRef = useRef(onFinished);
  const seedRef = useRef(seedProgress);
  seedRef.current = seedProgress;

  useEffect(() => {
    finishedRef.current = onFinished;
  }, [onFinished]);

  useEffect(() => {
    const seed = seedRef.current;
    setProgress(
      jobId && seed
        ? {
            progress: seed.progress ?? 0,
            step: seed.step ?? seed.stage ?? '',
            message: seed.message ?? '',
            stage: seed.stage ?? seed.step ?? '',
            current_beat: seed.current_beat ?? null,
            total_beats: seed.total_beats ?? null,
          }
        : EMPTY,
    );
    setJob(null);
    setConnectionError(null);
    if (!jobId) return;

    let closed = false;
    const source = new EventSource(`/api/jobs/${encodeURIComponent(jobId)}/events`);

    const finish = async () => {
      if (closed) return;
      closed = true;
      source.close();
      try {
        const final = await api.getJob(jobId);
        setJob(final);
        setProgress((p) => ({ ...p, progress: final.status === 'done' ? 100 : p.progress }));
        finishedRef.current?.(final);
      } catch (e) {
        setConnectionError(e instanceof Error ? e.message : String(e));
      }
    };

    source.addEventListener('progress', (ev) => {
      try {
        const data = JSON.parse((ev as MessageEvent<string>).data) as Partial<JobProgress>;
        setProgress((prev) => {
          const next: JobProgress = {
            progress: data.progress ?? data.percent ?? prev.progress,
            step: data.step ?? data.stage ?? prev.step,
            message: data.message ?? data.text ?? '',
          };
          if (data.stage !== undefined) next.stage = data.stage;
          else if (prev.stage !== undefined) next.stage = prev.stage;
          if (data.current !== undefined) next.current = data.current;
          if (data.total !== undefined) next.total = data.total;
          if (data.current_beat !== undefined) next.current_beat = data.current_beat;
          else if (prev.current_beat !== undefined) next.current_beat = prev.current_beat;
          if (data.total_beats !== undefined) next.total_beats = data.total_beats;
          else if (prev.total_beats !== undefined) next.total_beats = prev.total_beats;
          if (data.percent !== undefined) next.percent = data.percent;
          return next;
        });
      } catch {
        // Bỏ qua sự kiện hỏng.
      }
    });
    source.addEventListener('end', () => void finish());
    source.addEventListener('error', () => {
      // EventSource tự nối lại; chỉ khi đã đóng hẳn mới hỏi trạng thái job.
      if (source.readyState === EventSource.CLOSED) void finish();
    });

    return () => {
      closed = true;
      source.close();
    };
  }, [jobId]);

  const cancel = useCallback(async () => {
    if (jobId) await api.cancelJob(jobId);
  }, [jobId]);

  return { progress, job, connectionError, cancel };
}
