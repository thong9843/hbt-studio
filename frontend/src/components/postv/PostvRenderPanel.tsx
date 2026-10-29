import { useState, type ReactNode } from 'react';
import type { RenderOptions } from '../../api/types';
import { usePostvEditor } from '../../hooks/postvEditor';
import { useRenderJob } from '../../hooks/renderJob';
import { vi } from '../../i18n/vi';
import { ErrorNote } from '../ErrorNote';
import { PlayIcon, StopIcon } from '../icons';
import { Button, type ButtonTone } from '../ui/Button';
import { Progress } from '../ui/Progress';

const T = vi.postv.render;

interface Props {
  label: string;
  options: RenderOptions;
  tone?: ButtonTone;
  /** Lý do chưa dựng được (vô hiệu nút); `null` = dựng được. */
  blocked?: string | null;
  icon?: ReactNode;
}

/**
 * Nút dựng PostV dùng chung (Xem nhanh ở bước 4, Xuất bản đẹp ở bước 5): lưu dự án, gọi
 * `POST /render` qua `RenderJobProvider`, hiện tiến độ, nút Huỷ và video vừa dựng. Bản đầy đủ
 * (lịch sử, bìa, nội dung đăng) làm ở PV6.
 */
export function PostvRenderPanel({ label, options, tone = 'ink', blocked = null, icon }: Props) {
  const { project, flush } = usePostvEditor();
  const job = useRenderJob();
  const [error, setError] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);
  const mine = job.slug === project.slug;
  const running = mine && job.running;
  const finished = mine ? job.finished : null;
  const sameKind = finished?.preview === Boolean(options.preview);

  const launch = async () => {
    setError(null);
    setSaving(true);
    try {
      await flush();
      await job.start(project.slug, options);
    } catch (e) {
      setError(e);
    } finally {
      setSaving(false);
    }
  };

  const output = sameKind && finished?.status === 'done' ? finished.output : null;
  const percent = Math.round(job.percent);
  return (
    <div className="space-y-3" aria-live="polite">
      <Button
        tone={tone}
        size="lg"
        className="w-full"
        busy={saving || job.starting}
        disabled={running || (job.running && !mine) || Boolean(blocked)}
        reason={blocked ?? undefined}
        icon={icon ?? <PlayIcon size={20} />}
        onClick={() => void launch()}
      >
        {running ? T.busy : label}
      </Button>
      {blocked && <p className="text-small font-bold text-danger">{blocked}</p>}
      {running && (
        <div className="space-y-2">
          <Progress value={job.percent} label={T.progress} />
          <p className="text-small">
            <span className="tabular-nums">{percent}%</span>
            {job.step && <span> · {job.step}</span>}
          </p>
          <Button
            tone="soft"
            size="sm"
            icon={<StopIcon size={18} />}
            onClick={() => void job.cancel()}
          >
            {T.cancel}
          </Button>
        </div>
      )}
      <ErrorNote error={error ?? job.connectionError} />
      {sameKind && finished?.status === 'failed' && (
        <ErrorNote error={`${T.failed}: ${finished.error ?? ''}`} />
      )}
      {sameKind && finished?.status === 'cancelled' && (
        <p className="text-small text-muted">{T.cancelled}</p>
      )}
      {output && (
        <div className="space-y-2" data-slot="result">
          <video
            controls
            aria-label={T.player}
            className="w-full rounded-card bg-ink"
            src={output.video}
          />
          <p className="text-small tabular-nums text-muted">
            {T.meta(output.duration, output.fps, output.seconds)}
          </p>
          <div className="flex flex-wrap gap-2">
            <a className="ui-btn ui-btn-soft ui-btn-sm" href={output.video} download="video.mp4">
              {T.video}
            </a>
            <a
              className="ui-btn ui-btn-soft ui-btn-sm"
              href={output.publish}
              download="publish.txt"
            >
              {T.publish}
            </a>
          </div>
          {output.warnings.length > 0 && (
            <ul aria-label={T.warnings} className="list-disc pl-5 text-small">
              {output.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
