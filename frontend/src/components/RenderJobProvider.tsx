import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { api } from '../api/endpoints';
import type { ActiveJob, Job, RenderOptions } from '../api/types';
import {
  createRenderJobProgressStore,
  EMPTY_PROGRESS_SNAPSHOT,
  RenderJobContext,
  type AttachJobInput,
  type RenderJobStatusApi,
} from '../hooks/renderJob';
import { useToast } from '../hooks/toast';
import { useJob, type JobProgress } from '../hooks/useJob';
import { vi } from '../i18n/vi';

function toSnapshot(p: Partial<JobProgress> | null | undefined) {
  if (!p) return EMPTY_PROGRESS_SNAPSHOT;
  const step = p.step ?? p.stage ?? '';
  const rawPct = p.progress ?? p.percent;
  const percent =
    typeof rawPct === 'number' && Number.isFinite(rawPct) ? Math.max(0, Math.min(100, rawPct)) : 0;
  return {
    percent,
    step,
    stage: p.stage || step,
    message: p.message ?? '',
    currentBeat: p.current_beat ?? null,
    totalBeats: p.total_beats ?? null,
  };
}

/**
 * Giữ job dựng (HBT Core, PostV, StickV) và luồng SSE ở mức toàn app, để đổi màn không mất
 * tiến độ.
 * - Tiến độ % (`percent`, `step`, `stage`, `message`, `currentBeat`, `totalBeats`) được ghi thẳng
 *   vào `progressStore` (external store + `useSyncExternalStore`), giúp `RenderJobProvider` và các
 *   trang lớn (`StickvPage`, `<video>`, Inspector Tabs) re-render ĐÚNG 0 LẦN khi job chạy 1% → 100%.
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

  const progressStoreRef = useRef(createRenderJobProgressStore());
  const kindRef = useRef(kind);
  kindRef.current = kind;
  const completedJobIdsRef = useRef<Set<string>>(new Set());

  const handleProgress = useCallback((p: JobProgress) => {
    progressStoreRef.current.setSnapshot(toSnapshot(p));
  }, []);

  const { connectionError, cancel: cancelJob } = useJob(
    jobId,
    (job) => {
      if (job.status === 'running' || job.status === 'queued') {
        return;
      }
      setFinished(job);
      if (completedJobIdsRef.current.has(job.id)) {
        return;
      }
      completedJobIdsRef.current.add(job.id);
      void queryClient.invalidateQueries({ queryKey: ['renders', job.project] });
      void queryClient.invalidateQueries({ queryKey: ['projects'] });
      const isStickv = kindRef.current === 'stickv' || job.kind === 'stickv';
      const isCoreImages = kindRef.current === 'hbt_core_images' || job.kind === 'hbt_core_images';
      const isCorePrepare =
        kindRef.current === 'hbt_core_prepare' || job.kind === 'hbt_core_prepare';
      if (isStickv) {
        void queryClient.invalidateQueries({ queryKey: ['stickv-list'] });
        void queryClient.invalidateQueries({ queryKey: ['unified-renders'] });
        if (job.status === 'done') toast.info(vi.stickvJob.renderDone);
        else if (job.status === 'failed') toast.error(job.error || vi.stickvJob.renderFailed);
        else if (job.status === 'cancelled') toast.info(vi.stickvJob.renderCancelled);
      } else if (isCoreImages) {
        void queryClient.invalidateQueries({ queryKey: ['hbt-core-assets'] });
        void queryClient.invalidateQueries({ queryKey: ['project', job.project] });
        if (job.status === 'done') toast.info(vi.hbtCore.autoImage.doneToast);
        else if (job.status === 'failed') toast.error(job.error || vi.export.failed);
      } else if (isCorePrepare) {
        void queryClient.invalidateQueries({ queryKey: ['hbt-core-assets'] });
        void queryClient.invalidateQueries({ queryKey: ['project', job.project] });
        if (job.status === 'done') toast.info(vi.hbtCore.prepare.doneToast);
        else if (job.status === 'failed') toast.error(job.error || vi.export.failed);
      } else if (job.status === 'done') {
        toast.info(vi.export.done);
      }
    },
    seedProgress,
    {
      onProgress: handleProgress,
      externalProgressOnly: true,
    },
  );

  const jobIdRef = useRef(jobId);
  jobIdRef.current = jobId;
  const finishedRef = useRef(finished);
  finishedRef.current = finished;

  const attachJob = useCallback((input: AttachJobInput) => {
    if (jobIdRef.current === input.jobId && finishedRef.current === null) {
      return;
    }
    completedJobIdsRef.current.delete(input.jobId);
    const seed: Partial<JobProgress> = {
      progress: input.progress ?? 0,
      step: input.step ?? input.stage ?? '',
      stage: input.stage ?? input.step ?? '',
      message: input.message ?? '',
      current_beat: input.currentBeat ?? null,
      total_beats: input.totalBeats ?? null,
    };
    progressStoreRef.current.setSnapshot(toSnapshot(seed));
    setSlug(input.slug);
    setKind(input.kind);
    setOptions({ preview: Boolean(input.preview) });
    setFinished(null);
    setEstimate(input.estimateSeconds ?? null);
    setStartedAt(input.startedAt ?? Date.now() / 1000);
    setSeedProgress(seed);
    setJobId(input.jobId);
  }, []);

  const start = useCallback(
    async (target: string, opts: RenderOptions, estimate: number | null = null) => {
      setStarting(true);
      try {
        const res = await api.startRender(target, opts);
        progressStoreRef.current.setSnapshot(EMPTY_PROGRESS_SNAPSHOT);
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

  const resumed = useRef(false);
  useEffect(() => {
    if (resumed.current) return;
    resumed.current = true;
    api
      .listActiveJobs()
      .then((rows) => {
        const renders = Array.isArray(rows) ? rows.filter((r) => r.kind !== 'voice') : [];
        const head = renders.find((r) => r.status === 'running') ?? renders[0] ?? null;
        if (!head || jobIdRef.current !== null) return;
        const seed: Partial<JobProgress> = {
          progress: head.progress ?? 0,
          step: head.step ?? head.stage ?? '',
          stage: head.stage ?? head.step ?? '',
          message: '',
          current_beat: head.current_beat ?? null,
          total_beats: head.total_beats ?? null,
        };
        progressStoreRef.current.setSnapshot(toSnapshot(seed));
        setSlug(head.slug);
        setKind(head.kind);
        setOptions({ preview: head.kind === 'preview' || head.mode === 'preview' });
        setFinished(null);
        setStartedAt(head.started_at ?? null);
        setSeedProgress(seed);
        setJobId(head.id);
      })
      .catch(() => undefined);
  }, []);

  const cancel = useCallback(() => cancelJob(), [cancelJob]);

  const running = jobId !== null && finished === null && !connectionError;
  const value: RenderJobStatusApi = useMemo(
    () => ({
      slug,
      jobId,
      kind,
      running,
      starting,
      startedAt,
      finished,
      connectionError,
      options,
      estimateSeconds,
      start,
      attachJob,
      cancel,
      progressStore: progressStoreRef.current,
    }),
    [
      slug,
      jobId,
      kind,
      running,
      starting,
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
