import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { api } from '../api/endpoints';
import type { ActiveJob, Job, RenderOptions } from '../api/types';
import { RenderJobContext, type AttachJobInput, type RenderJobApi } from '../hooks/renderJob';
import { useToast } from '../hooks/toast';
import { useJob, type JobProgress } from '../hooks/useJob';
import { vi } from '../i18n/vi';

/**
 * Giữ job dựng (HBT Core, PostV, StickV) và luồng SSE ở mức toàn app, để đổi màn không mất
 * tiến độ. `useJob` chỉ mở `EventSource` khi có `jobId` và đóng khi job kết thúc, nên lúc rảnh
 * không có kết nối hay request nào (13.B3.2 luật 6).
 */
export function RenderJobProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [slug, setSlug] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [kind, setKind] = useState<ActiveJob['kind'] | null>(null);
  const [options, setOptions] = useState<RenderOptions>({});
  const [finished, setFinished] = useState<Job | null>(null);
  const [starting, setStarting] = useState(false);
  const [estimateSeconds, setEstimate] = useState<number | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [seedProgress, setSeedProgress] = useState<Partial<JobProgress> | null>(null);

  const kindRef = useRef(kind);
  kindRef.current = kind;

  const {
    progress,
    connectionError,
    cancel: cancelJob,
  } = useJob(
    jobId,
    (job) => {
      setFinished(job);
      void queryClient.invalidateQueries({ queryKey: ['renders', job.project] });
      void queryClient.invalidateQueries({ queryKey: ['projects'] });
      const isStickv = kindRef.current === 'stickv' || job.kind === 'stickv';
      if (isStickv) {
        void queryClient.invalidateQueries({ queryKey: ['stickv-list'] });
        void queryClient.invalidateQueries({ queryKey: ['unified-renders'] });
        if (job.status === 'done') toast.info(vi.stickvJob.renderDone);
        else if (job.status === 'failed') toast.error(job.error || vi.stickvJob.renderFailed);
        else if (job.status === 'cancelled') toast.info(vi.stickvJob.renderCancelled);
      } else if (job.status === 'done') {
        toast.info(vi.export.done);
      }
    },
    seedProgress,
  );

  const jobIdRef = useRef(jobId);
  jobIdRef.current = jobId;
  const finishedRef = useRef(finished);
  finishedRef.current = finished;

  const attachJob = useCallback((input: AttachJobInput) => {
    if (jobIdRef.current === input.jobId && finishedRef.current === null) {
      // Đang mở sẵn đúng luồng SSE này -> giữ nguyên không reset tiến độ
      return;
    }
    setSlug(input.slug);
    setKind(input.kind);
    setOptions({ preview: Boolean(input.preview) });
    setFinished(null);
    setEstimate(input.estimateSeconds ?? null);
    setStartedAt(input.startedAt ?? Date.now() / 1000);
    setSeedProgress({
      progress: input.progress ?? 0,
      step: input.step ?? input.stage ?? '',
      stage: input.stage ?? input.step ?? '',
      message: input.message ?? '',
      current_beat: input.currentBeat ?? null,
      total_beats: input.totalBeats ?? null,
    });
    setJobId(input.jobId);
  }, []);

  const start = useCallback(
    async (target: string, opts: RenderOptions, estimate: number | null = null) => {
      setStarting(true);
      try {
        const res = await api.startRender(target, opts);
        setSlug(target);
        setKind(opts.preview ? 'preview' : 'final');
        setOptions(opts);
        setFinished(null);
        setEstimate(estimate);
        setStartedAt(Date.now() / 1000);
        setSeedProgress(null);
        setJobId(res.job_id);
      } finally {
        setStarting(false);
      }
    },
    [],
  );

  // Mở app (hoặc tải lại trang) khi backend vẫn đang dựng: hỏi `GET /jobs` đúng một lần rồi nối lại
  // SSE của job đầu hàng. Không poll (13.B3.2 luật 6); lỗi mạng thì bỏ qua, 409 của máy chủ vẫn chặn.
  const resumed = useRef(false);
  useEffect(() => {
    if (resumed.current) return;
    resumed.current = true;
    api
      .listActiveJobs()
      .then((rows) => {
        const renders = Array.isArray(rows) ? rows.filter((r) => r.kind !== 'voice') : [];
        const head = renders.find((r) => r.status === 'running') ?? renders[0] ?? null;
        if (!head || jobIdRef.current !== null) return; // người dùng đã tự bắt đầu một job
        setSlug(head.slug);
        setKind(head.kind);
        setOptions({ preview: head.kind === 'preview' || head.mode === 'preview' });
        setFinished(null);
        setStartedAt(head.started_at ?? null);
        setSeedProgress({
          progress: head.progress ?? 0,
          step: head.step ?? head.stage ?? '',
          stage: head.stage ?? head.step ?? '',
          message: '',
          current_beat: head.current_beat ?? null,
          total_beats: head.total_beats ?? null,
        });
        setJobId(head.id);
      })
      .catch(() => undefined);
  }, []);

  const cancel = useCallback(() => cancelJob(), [cancelJob]);

  const running = jobId !== null && finished === null && !connectionError;
  const value: RenderJobApi = useMemo(
    () => ({
      slug,
      jobId,
      kind,
      running,
      starting,
      percent: progress.progress,
      step: progress.step,
      stage: progress.stage || progress.step,
      message: progress.message,
      currentBeat: progress.current_beat ?? null,
      totalBeats: progress.total_beats ?? null,
      startedAt,
      finished,
      connectionError,
      options,
      estimateSeconds,
      start,
      attachJob,
      cancel,
    }),
    [
      slug,
      jobId,
      kind,
      running,
      starting,
      progress,
      startedAt,
      finished,
      connectionError,
      options,
      estimateSeconds,
      start,
      attachJob,
      cancel,
    ],
  );

  return <RenderJobContext.Provider value={value}>{children}</RenderJobContext.Provider>;
}
