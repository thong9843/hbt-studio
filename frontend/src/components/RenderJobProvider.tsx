import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useMemo, useState, type ReactNode } from 'react';
import { api } from '../api/endpoints';
import type { Job, RenderOptions } from '../api/types';
import { RenderJobContext, type RenderJobApi } from '../hooks/renderJob';
import { useToast } from '../hooks/toast';
import { useJob } from '../hooks/useJob';
import { vi } from '../i18n/vi';

/**
 * Giữ job dựng và luồng SSE ở mức toàn app, để đổi màn không mất tiến độ. `useJob` chỉ mở
 * `EventSource` khi có `jobId` và đóng khi job kết thúc, nên lúc rảnh không có kết nối hay request
 * nào (13.B3.2 luật 6).
 */
export function RenderJobProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [slug, setSlug] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [options, setOptions] = useState<RenderOptions>({});
  const [finished, setFinished] = useState<Job | null>(null);
  const [starting, setStarting] = useState(false);
  const [estimateSeconds, setEstimate] = useState<number | null>(null);

  const {
    progress,
    connectionError,
    cancel: cancelJob,
  } = useJob(jobId, (job) => {
    setFinished(job);
    void queryClient.invalidateQueries({ queryKey: ['renders', job.project] });
    void queryClient.invalidateQueries({ queryKey: ['projects'] });
    if (job.status === 'done') toast.info(vi.export.done);
  });

  const start = useCallback(
    async (target: string, opts: RenderOptions, estimate: number | null = null) => {
      setStarting(true);
      try {
        const res = await api.startRender(target, opts);
        setSlug(target);
        setOptions(opts);
        setFinished(null);
        setEstimate(estimate);
        setJobId(res.job_id);
      } finally {
        setStarting(false);
      }
    },
    [],
  );

  const cancel = useCallback(() => cancelJob(), [cancelJob]);

  const running = jobId !== null && finished === null && !connectionError;
  const value: RenderJobApi = useMemo(
    () => ({
      slug,
      jobId,
      running,
      starting,
      percent: progress.progress,
      step: progress.step,
      message: progress.message,
      finished,
      connectionError,
      options,
      estimateSeconds,
      start,
      cancel,
    }),
    [
      slug,
      jobId,
      running,
      starting,
      progress,
      finished,
      connectionError,
      options,
      estimateSeconds,
      start,
      cancel,
    ],
  );

  return <RenderJobContext.Provider value={value}>{children}</RenderJobContext.Provider>;
}
