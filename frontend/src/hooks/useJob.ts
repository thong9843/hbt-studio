import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api/endpoints';
import type { Job } from '../api/types';

export interface JobProgress {
  progress: number;
  step: string;
  message: string;
}

const EMPTY: JobProgress = { progress: 0, step: '', message: '' };

/**
 * Theo dõi một job dựng video qua SSE (`/api/jobs/{id}/events`). Khi có sự kiện `end` (hoặc mất kết
 * nối) thì đọc lại `GET /jobs/{id}` để có URL file đầu ra.
 */
export function useJob(jobId: string | null, onFinished?: (job: Job) => void) {
  const [progress, setProgress] = useState<JobProgress>(EMPTY);
  const [job, setJob] = useState<Job | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const finishedRef = useRef(onFinished);

  useEffect(() => {
    finishedRef.current = onFinished;
  }, [onFinished]);

  useEffect(() => {
    setProgress(EMPTY);
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
        setProgress({
          progress: data.progress ?? 0,
          step: data.step ?? '',
          message: data.message ?? '',
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
