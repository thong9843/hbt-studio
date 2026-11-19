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

export interface UseJobOptions {
  onProgress?: (progress: JobProgress) => void;
  /** Khi bật, đẩy tiến độ sang external store qua `onProgress` mà không setState nội bộ mỗi nhịp. */
  externalProgressOnly?: boolean;
}

const EMPTY: JobProgress = { progress: 0, step: '', message: '' };
export const PROGRESS_THROTTLE_MS = 150;

/**
 * Single-Stream SSE Registry: đảm bảo mỗi `jobId` chỉ mở tối đa 1 kết nối `EventSource`
 * trên toàn ứng dụng, triệt tiêu hoàn toàn bão kết nối trùng lặp gây đơ trình duyệt.
 */
const activeStreams = new Map<string, EventSource>();

export function getActiveStreamCount(): number {
  return activeStreams.size;
}

export function resetActiveStreams(): void {
  for (const es of activeStreams.values()) {
    try {
      es.close();
    } catch {
      // Bỏ qua lỗi khi đóng kết nối cũ
    }
  }
  activeStreams.clear();
}

function mergeProgress(prev: JobProgress, data: Partial<JobProgress>): JobProgress {
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
}

/**
 * Theo dõi một job dựng video qua SSE (`/api/jobs/{id}/events`). Khi có sự kiện `end` (hoặc mất kết
 * nối) thì đọc lại `GET /jobs/{id}` để có URL file đầu ra.
 * - Singleton `Map<jobId, EventSource>`: tối đa 1 kết nối cho mỗi `jobId`.
 * - Throttle `150ms` cho các sự kiện `progress` dồn dập trong cùng bước, chống re-render làm lag tab.
 */
export function useJob(
  jobId: string | null,
  onFinished?: (job: Job) => void,
  seedProgress?: Partial<JobProgress> | null,
  options?: UseJobOptions,
) {
  const [progress, setProgress] = useState<JobProgress>(EMPTY);
  const [job, setJob] = useState<Job | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const finishedRef = useRef(onFinished);
  const onProgressRef = useRef(options?.onProgress);
  onProgressRef.current = options?.onProgress;
  const externalOnlyRef = useRef(Boolean(options?.externalProgressOnly));
  externalOnlyRef.current = Boolean(options?.externalProgressOnly);
  const seedRef = useRef(seedProgress);
  seedRef.current = seedProgress;
  const latestProgressRef = useRef<JobProgress>(EMPTY);
  const lastFlushAtRef = useRef<number>(0);
  const throttleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const notifiedJobIdRef = useRef<string | null>(null);

  useEffect(() => {
    finishedRef.current = onFinished;
  }, [onFinished]);

  useEffect(() => {
    const emitProgress = (next: JobProgress) => {
      onProgressRef.current?.(next);
      if (!externalOnlyRef.current) {
        setProgress(next);
      }
    };

    if (throttleTimerRef.current !== null) {
      clearTimeout(throttleTimerRef.current);
      throttleTimerRef.current = null;
    }
    lastFlushAtRef.current = 0;
    notifiedJobIdRef.current = null;
    const seed = seedRef.current;
    const initial: JobProgress =
      jobId && seed
        ? {
            progress: seed.progress ?? 0,
            step: seed.step ?? seed.stage ?? '',
            message: seed.message ?? '',
            stage: seed.stage ?? seed.step ?? '',
            current_beat: seed.current_beat ?? null,
            total_beats: seed.total_beats ?? null,
          }
        : EMPTY;
    latestProgressRef.current = initial;
    emitProgress(initial);
    setJob(null);
    setConnectionError(null);
    if (!jobId) return;

    let closed = false;
    const existing = activeStreams.get(jobId);
    const ctorInstances = (EventSource as unknown as { instances?: EventSource[] }).instances;
    const canReuse =
      existing &&
      existing.readyState !== EventSource.CLOSED &&
      (!Array.isArray(ctorInstances) || ctorInstances.includes(existing));
    const source = canReuse
      ? existing
      : new EventSource(`/api/jobs/${encodeURIComponent(jobId)}/events`);
    activeStreams.set(jobId, source);

    const clearTimer = () => {
      if (throttleTimerRef.current !== null) {
        clearTimeout(throttleTimerRef.current);
        throttleTimerRef.current = null;
      }
    };

    const closeStream = () => {
      clearTimer();
      source.close();
      if (activeStreams.get(jobId) === source) {
        activeStreams.delete(jobId);
      }
    };

    const finish = async (fromEndEvent: boolean) => {
      if (closed) return;
      clearTimer();
      try {
        const final = await api.getJob(jobId);
        // Nếu kết nối SSE ngắt tạm thời nhưng backend vẫn đang chạy/chờ -> KHÔNG báo hoàn tất giả
        if (!fromEndEvent && (final.status === 'running' || final.status === 'queued')) {
          const synced = mergeProgress(latestProgressRef.current, {
            progress: final.progress ?? latestProgressRef.current.progress,
            step: final.step ?? final.stage ?? latestProgressRef.current.step,
            stage: final.stage ?? final.step,
            current_beat: final.current_beat,
            total_beats: final.total_beats,
          });
          latestProgressRef.current = synced;
          emitProgress(synced);
          return;
        }
        closed = true;
        closeStream();
        setJob(final);
        const terminalProgress: JobProgress = {
          ...latestProgressRef.current,
          progress: final.status === 'done' ? 100 : latestProgressRef.current.progress,
        };
        latestProgressRef.current = terminalProgress;
        emitProgress(terminalProgress);
        if (notifiedJobIdRef.current !== jobId) {
          notifiedJobIdRef.current = jobId;
          finishedRef.current?.(final);
        }
      } catch (e) {
        closed = true;
        closeStream();
        setConnectionError(e instanceof Error ? e.message : String(e));
      }
    };

    const onProgress = (ev: Event) => {
      if (closed) return;
      try {
        const data = JSON.parse((ev as MessageEvent<string>).data) as Partial<JobProgress>;
        const prev = latestProgressRef.current;
        const next = mergeProgress(prev, data);
        latestProgressRef.current = next;

        const now = Date.now();
        const stepChanged = next.step !== prev.step || next.stage !== prev.stage;
        const isFirstOrBoundary =
          lastFlushAtRef.current === 0 || stepChanged || next.progress >= 100;
        const elapsed = now - lastFlushAtRef.current;

        if (isFirstOrBoundary || elapsed >= PROGRESS_THROTTLE_MS) {
          clearTimer();
          lastFlushAtRef.current = now;
          emitProgress(next);
        } else if (throttleTimerRef.current === null) {
          const remain = Math.max(16, PROGRESS_THROTTLE_MS - elapsed);
          throttleTimerRef.current = setTimeout(() => {
            throttleTimerRef.current = null;
            if (!closed) {
              lastFlushAtRef.current = Date.now();
              emitProgress(latestProgressRef.current);
            }
          }, remain);
        }
      } catch {
        // Bỏ qua sự kiện hỏng.
      }
    };

    const onEnd = () => void finish(true);
    const onError = () => {
      // EventSource tự nối lại; chỉ khi đã đóng hẳn mới hỏi trạng thái job.
      if (source.readyState === EventSource.CLOSED) void finish(false);
    };

    source.addEventListener('progress', onProgress);
    source.addEventListener('end', onEnd);
    source.addEventListener('error', onError);

    return () => {
      closed = true;
      try {
        source.removeEventListener?.('progress', onProgress);
        source.removeEventListener?.('end', onEnd);
        source.removeEventListener?.('error', onError);
      } finally {
        closeStream();
      }
    };
  }, [jobId]);

  const cancel = useCallback(async () => {
    if (jobId) await api.cancelJob(jobId);
  }, [jobId]);

  return { progress, job, connectionError, cancel };
}
