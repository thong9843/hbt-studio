import { useMutation, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../../api/endpoints';
import type { PostvProject } from '../../api/types';
import { usePostvEditor } from '../../hooks/postvEditor';
import { useJob } from '../../hooks/useJob';
import { vi } from '../../i18n/vi';
import { ErrorNote } from '../ErrorNote';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { Chip } from '../ui/Chip';
import { Progress } from '../ui/Progress';

const T = vi.postv.auto;
const COMMENT_COUNTS = [2, 3, 4, 5];

interface Props {
  project: PostvProject;
  disabled?: boolean;
}

export function PostvAutoPanel({ project, disabled }: Props) {
  const { flush, update } = usePostvEditor();
  const navigate = useNavigate();

  const stylesQuery = useQuery({
    queryKey: ['postv-styles'],
    queryFn: api.getPostvStyles,
    staleTime: Infinity,
  });

  const styles = stylesQuery.data ?? T.fallbackStyles;
  const initialStyle = project.auto?.style ?? 'ke-chuyen';
  const initialCount = project.auto?.comment_count ?? 3;

  const [selectedStyle, setSelectedStyle] = useState(initialStyle);
  const [commentCount, setCommentCount] = useState(initialCount);
  const [jobId, setJobId] = useState<string | null>(null);

  const { job, progress, cancel } = useJob(jobId);
  const status = job?.status ?? (jobId ? 'running' : null);

  const startAuto = useMutation({
    mutationFn: async () => {
      await flush();
      update((p) => ({
        ...p,
        auto: { style: selectedStyle, comment_count: commentCount },
      }));
      return api.startPostvAuto(project.slug, {
        style: selectedStyle,
        comment_count: commentCount,
      });
    },
    onSuccess: (res) => {
      setJobId(res.job_id);
    },
  });

  const isRunning = Boolean(jobId && (status === 'queued' || status === 'running'));
  const isDone = status === 'done';
  const isFailed = status === 'failed';
  const isVieneuError =
    isFailed && (job?.error?.toLowerCase().includes('vieneu') || job?.error?.includes('giọng'));

  return (
    <Card as="section" aria-label={T.title} className="space-y-4">
      <div>
        <h2 className="text-h2 font-bold">{T.title}</h2>
        <p className="text-small text-muted">{T.lead}</p>
      </div>

      <div className="space-y-2">
        <label className="text-small font-bold text-muted">{T.styleLabel}</label>
        <div className="flex flex-wrap gap-2" role="group" aria-label={T.styleLabel}>
          {styles.map((s) => (
            <Chip
              key={s.id}
              selected={selectedStyle === s.id}
              disabled={isRunning}
              onClick={() => setSelectedStyle(s.id)}
            >
              {s.label}
            </Chip>
          ))}
        </div>
      </div>

      <div className="space-y-2">
        <label className="text-small font-bold text-muted">{T.commentsLabel}</label>
        <div className="flex flex-wrap gap-2" role="group" aria-label={T.commentsLabel}>
          {COMMENT_COUNTS.map((n) => (
            <Chip
              key={n}
              selected={commentCount === n}
              disabled={isRunning}
              onClick={() => setCommentCount(n)}
            >
              {n}
            </Chip>
          ))}
        </div>
      </div>

      {isRunning && (
        <div className="space-y-2 rounded-inner bg-soft p-3">
          <div className="flex items-center justify-between">
            <span className="text-small font-semibold">{progress.message || T.submitting}</span>
            <span className="num text-tiny text-muted">{Math.round(progress.progress)}%</span>
          </div>
          <Progress value={progress.progress} label={T.title} />
          <div className="flex justify-end pt-1">
            <Button tone="soft" size="sm" onClick={() => cancel()} aria-label={T.cancel}>
              {T.cancel}
            </Button>
          </div>
        </div>
      )}

      {isDone && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-inner bg-ok/10 p-3 text-ok">
          <span className="text-small font-bold">Đã tạo tự động hoàn tất!</span>
          <Button tone="ink" size="sm" onClick={() => navigate('preview')}>
            {T.goToPreview}
          </Button>
        </div>
      )}

      {isVieneuError && (
        <div className="space-y-2 rounded-inner border border-amber-500/40 bg-amber-500/10 p-3 text-amber-900 dark:text-amber-200">
          <p className="text-small font-semibold">{T.missingVieneu}</p>
          <Button tone="soft" size="sm" onClick={() => navigate('script')}>
            {T.goToScript}
          </Button>
        </div>
      )}

      {isFailed && !isVieneuError && <ErrorNote error={job?.error} />}

      <ErrorNote error={startAuto.error} />

      {!isRunning && !isDone && (
        <Button
          tone="accent"
          size="lg"
          className="w-full"
          disabled={disabled || startAuto.isPending}
          busy={startAuto.isPending}
          onClick={() => startAuto.mutate()}
        >
          {T.submit}
        </Button>
      )}
    </Card>
  );
}
