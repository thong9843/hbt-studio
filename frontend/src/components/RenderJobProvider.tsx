import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { api } from '../api/endpoints';
import type { ActiveJob, Job, RenderOptions, StudioEngine } from '../api/types';
import {
  createRenderJobProgressStore,
  EMPTY_PROGRESS_SNAPSHOT,
  inferJobEngine,
  RenderJobContext,
  resolveJobRoute,
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
    ...(p.current !== undefined ? { current: p.current } : {}),
    ...(p.total !== undefined ? { total: p.total } : {}),
    ...(p.status !== undefined ? { status: p.status } : {}),
    ...(p.phase !== undefined ? { phase: p.phase } : {}),
    ...(p.data !== undefined ? { data: p.data } : {}),
    ...(p.timings !== undefined ? { timings: p.timings } : {}),
  };
}

/**
 * Giữ job dựng (HBT Core, PostV, Chatting, StickV) và luồng SSE ở mức toàn app, để đổi màn không mất
 * tiến độ. Tiến độ % được đẩy qua `jobProgressStore` (`useSyncExternalStore` + throttle 250ms).
 */
export function RenderJobProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [slug, setSlug] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [kind, setKind] = useState<ActiveJob['kind'] | null>(null);
  const [engine, setEngine] = useState<StudioEngine | null>(null);
  const [title, setTitle] = useState<string | null>(null);
  const [route, setRoute] = useState<string | null>(null);
  const [options, setOptions] = useState<RenderOptions>({});
  const [finished, setFinished] = useState<Job | null>(null);
  const [starting, setStarting] = useState(false);
  const [estimateSeconds, setEstimate] = useState<number | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [seedProgress, setSeedProgress] = useState<Partial<JobProgress> | null>(null);

  const progressStoreRef = useRef(createRenderJobProgressStore());
  const kindRef = useRef(kind);
  kindRef.current = kind;
  const engineRef = useRef(engine);
  engineRef.current = engine;
  const completedJobIdsRef = useRef<Set<string>>(new Set());

  const handleProgress = useCallback((p: JobProgress) => {
    const immediate = p.data !== undefined || p.status === 'waiting_pick';
    progressStoreRef.current.setSnapshot(toSnapshot(p), immediate);
  }, []);

  const adoptActiveJob = useCallback((head: ActiveJob) => {
    const resolvedEngine = inferJobEngine(head.kind, head.engine);
    const resolvedRoute = resolveJobRoute(resolvedEngine, head.kind, head.slug, head.route);
    const seed: Partial<JobProgress> = {
      progress: head.progress ?? 0,
      step: head.step ?? head.stage ?? '',
      stage: head.stage ?? head.step ?? '',
      message: head.stage || head.step || '',
      current_beat: head.current_beat ?? null,
      total_beats: head.total_beats ?? null,
    };
    progressStoreRef.current.setSnapshot(toSnapshot(seed), true);
    setSlug(head.slug);
    setKind(head.kind);
    setEngine(resolvedEngine);
    setTitle(head.title || head.slug);
    setRoute(resolvedRoute);
    setOptions({ preview: head.kind === 'preview' || head.mode === 'preview' });
    setFinished(null);
    setEstimate(null);
    setStartedAt(head.started_at ?? null);
    setSeedProgress(seed);
    setJobId(head.id);
  }, []);

  const jobIdRef = useRef(jobId);
  jobIdRef.current = jobId;
  const finishedRef = useRef(finished);
  finishedRef.current = finished;

  const { connectionError, cancel: cancelJob } = useJob(
    jobId,
    (job) => {
      if (job.status === 'running' || job.status === 'queued') {
        return;
      }
      setFinished(job);
      if (!completedJobIdsRef.current.has(job.id)) {
        completedJobIdsRef.current.add(job.id);
        const effEngine = inferJobEngine(kindRef.current ?? job.kind, engineRef.current ?? job.engine);
        void queryClient.invalidateQueries({ queryKey: ['renders', job.project] });
        void queryClient.invalidateQueries({ queryKey: ['projects'] });
        void queryClient.invalidateQueries({ queryKey: ['unified-renders'] });
        if (effEngine === 'stickv') {
          void queryClient.invalidateQueries({ queryKey: ['stickv-list'] });
          if (job.status === 'done') toast.info(vi.stickvJob.renderDone);
          else if (job.status === 'failed') toast.error(job.error || vi.stickvJob.renderFailed);
          else if (job.status === 'cancelled') toast.info(vi.stickvJob.renderCancelled);
        } else if (kindRef.current === 'hbt_core_images' || job.kind === 'hbt_core_images') {
          void queryClient.invalidateQueries({ queryKey: ['hbt-core-assets'] });
          void queryClient.invalidateQueries({ queryKey: ['project', job.project] });
          if (job.status === 'done') toast.info(vi.hbtCore.autoImage.doneToast);
          else if (job.status === 'failed') toast.error(job.error || vi.export.failed);
        } else if (kindRef.current === 'hbt_core_prepare' || job.kind === 'hbt_core_prepare') {
          void queryClient.invalidateQueries({ queryKey: ['hbt-core-assets'] });
          void queryClient.invalidateQueries({ queryKey: ['project', job.project] });
          if (job.status === 'done') toast.info(vi.hbtCore.prepare.doneToast);
          else if (job.status === 'failed') toast.error(job.error || vi.export.failed);
        } else if (effEngine === 'chatting') {
          void queryClient.invalidateQueries({ queryKey: ['chattingProject', job.slug ?? job.project] });
          void queryClient.invalidateQueries({ queryKey: ['chattingJob', job.slug ?? job.project] });
          void queryClient.invalidateQueries({ queryKey: ['chattingProjects'] });
          if (job.status === 'done') toast.info(vi.export.done);
          else if (job.status === 'failed') toast.error(job.error || vi.export.failed);
        } else if (job.status === 'done') {
          toast.info(vi.export.done);
        }
      }

      // Kiểm tra hàng đợi: nếu còn job queued khác đang chờ thì tự động nối tiếp ngay
      api
        .listActiveJobs()
        .then((rows) => {
          const active = Array.isArray(rows)
            ? rows.filter((r) => r.kind !== 'voice' && r.id !== job.id)
            : [];
          const next = active.find((r) => r.status === 'running') ?? active[0] ?? null;
          if (next && jobIdRef.current === job.id) {
            adoptActiveJob(next);
          }
        })
        .catch(() => undefined);
    },
    seedProgress,
    {
      onProgress: handleProgress,
      externalProgressOnly: true,
    },
  );

  const attachJob = useCallback(
    (input: AttachJobInput) => {
      if (jobIdRef.current === input.jobId && finishedRef.current === null) {
        return;
      }
      completedJobIdsRef.current.delete(input.jobId);
      const resolvedEngine = inferJobEngine(input.kind, input.engine);
      const resolvedRoute = resolveJobRoute(resolvedEngine, input.kind, input.slug, input.route);
      const seed: Partial<JobProgress> = {
        progress: input.progress ?? 0,
        step: input.step ?? input.stage ?? '',
        stage: input.stage ?? input.step ?? '',
        message: input.message ?? '',
        current_beat: input.currentBeat ?? null,
        total_beats: input.totalBeats ?? null,
      };
      progressStoreRef.current.setSnapshot(toSnapshot(seed), true);
      setSlug(input.slug);
      setKind(input.kind);
      setEngine(resolvedEngine);
      setTitle(input.title || input.slug);
      setRoute(resolvedRoute);
      setOptions({ preview: Boolean(input.preview) });
      setFinished(null);
      setEstimate(input.estimateSeconds ?? null);
      setStartedAt(input.startedAt ?? Date.now() / 1000);
      setSeedProgress(seed);
      setJobId(input.jobId);
    },
    [],
  );

  const start = useCallback(
    async (target: string, opts: RenderOptions, estimate: number | null = null) => {
      setStarting(true);
      try {
        const res = await api.startRender(target, opts);
        const startKind: ActiveJob['kind'] = opts.preview ? 'preview' : 'final';
        progressStoreRef.current.setSnapshot(EMPTY_PROGRESS_SNAPSHOT, true);
        setSlug(target);
        setKind(startKind);
        setEngine('core');
        setTitle(target);
        setRoute(`/p/${encodeURIComponent(target)}/export`);
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
        adoptActiveJob(head);
      })
      .catch(() => undefined);
  }, [adoptActiveJob]);

  const cancel = useCallback(() => cancelJob(), [cancelJob]);

  const running = jobId !== null && finished === null && !connectionError;
  const value: RenderJobStatusApi = useMemo(
    () => ({
      slug,
      jobId,
      kind,
      engine,
      title,
      route,
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
      engine,
      title,
      route,
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
