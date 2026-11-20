import { useQuery } from '@tanstack/react-query';
import { useState, type ReactNode, type RefObject } from 'react';
import { api } from '../../api/endpoints';
import type { RenderOptions } from '../../api/types';
import { usePostvEditor } from '../../hooks/postvEditor';
import { useRenderJob } from '../../hooks/renderJob';
import { vi } from '../../i18n/vi';
import { ErrorNote } from '../ErrorNote';
import { DownloadIcon, FolderIcon, PlayIcon, StopIcon } from '../icons';
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
  /** Video lịch sử được chọn (nếu khác bản mới nhất). */
  overrideVideoUrl?: string | null;
  /** Mở thư mục chứa video xuất. */
  onOpenFolder?: () => void;
  /** Ref tới thẻ `<video>` để giải phóng file handle khi xoá lịch sử trên Windows. */
  videoRef?: RefObject<HTMLVideoElement>;
}

/**
 * Nút dựng PostV dùng chung (Xem nhanh ở bước 4, Xuất bản đẹp ở bước 5): lưu dự án, gọi
 * `POST /render` qua `RenderJobProvider`, hiện tiến độ chi tiết, khung xem trước 9:16 gọn ở giữa
 * và các nút thao tác chính (Tải video, Mở thư mục, Render lại).
 */
export function PostvRenderPanel({
  label,
  options,
  tone = 'ink',
  blocked = null,
  icon,
  overrideVideoUrl = null,
  onOpenFolder,
  videoRef,
}: Props) {
  const { project, flush } = usePostvEditor();
  const job = useRenderJob();
  const [error, setError] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);
  const mine = job.slug === project.slug;
  const running = mine && job.running;
  const finished = mine ? job.finished : null;
  const sameKind = finished?.preview === Boolean(options.preview);

  const renders = useQuery({
    queryKey: ['renders', project.slug],
    queryFn: () => api.listRenders(project.slug),
    retry: false,
  });

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

  const history = renders.data ?? [];
  const latestRender = history.find(
    (r) => Boolean(r.preview) === Boolean(options.preview) && Boolean(r.video),
  );

  const fallbackOutput = latestRender?.video
    ? {
        video: latestRender.video,
        publish: latestRender.publish ?? '',
        duration: latestRender.duration ?? 0,
        fps: latestRender.fps ?? 30,
        seconds: latestRender.duration ?? 0,
        warnings: [] as string[],
      }
    : null;

  const output =
    (sameKind && finished?.status === 'done' ? finished.output : null) ?? fallbackOutput;
  const activeVideoUrl = overrideVideoUrl ?? output?.video ?? null;
  const percent = Math.round(job.percent);
  return (
    <div className="space-y-4" aria-live="polite">
      {activeVideoUrl && (
        <div
          className="mx-auto w-full max-w-[240px] overflow-hidden rounded-2xl border border-line bg-black shadow-lg"
          data-slot="compact-preview"
        >
          <video
            ref={videoRef}
            key={activeVideoUrl}
            controls
            playsInline
            aria-label={T.player}
            className="aspect-[9/16] w-full bg-black object-contain"
            src={activeVideoUrl}
          />
        </div>
      )}

      {running && (
        <div className="space-y-2 rounded-xl border border-line bg-soft/60 p-3">
          <Progress value={job.percent} label={T.progress} />
          <div className="flex items-center justify-between gap-2 text-small">
            <span className="truncate font-semibold text-ink">
              <span className="tabular-nums text-brand">{percent}%</span>
              {job.step && <span> · {job.step}</span>}
            </span>
            <Button
              tone="soft"
              size="sm"
              icon={<StopIcon size={16} />}
              onClick={() => void job.cancel()}
            >
              {T.cancel}
            </Button>
          </div>
        </div>
      )}

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
      <ErrorNote error={error ?? job.connectionError} />
      {sameKind && finished?.status === 'failed' && (
        <ErrorNote error={`${T.failed}: ${finished.error ?? ''}`} />
      )}
      {sameKind && finished?.status === 'cancelled' && (
        <p className="text-small text-muted">{T.cancelled}</p>
      )}
      {output && (
        <div className="space-y-2" data-slot="result">
          <p className="text-center text-small tabular-nums text-muted">
            {T.meta(output.duration, output.fps, output.seconds)}
          </p>
          <div className="flex flex-wrap items-center justify-center gap-2">
            <a
              className="ui-btn ui-btn-soft ui-btn-sm inline-flex items-center gap-1.5"
              href={output.video}
              download="video.mp4"
            >
              <DownloadIcon size={15} />
              {T.video}
            </a>
            {onOpenFolder && (
              <Button tone="soft" size="sm" icon={<FolderIcon size={15} />} onClick={onOpenFolder}>
                {T.openFolder}
              </Button>
            )}
            <Button
              tone="soft"
              size="sm"
              icon={<PlayIcon size={15} />}
              disabled={running || (job.running && !mine) || Boolean(blocked)}
              onClick={() => void launch()}
            >
              {T.reRender}
            </Button>
            {output.publish && (
              <a
                className="ui-btn ui-btn-soft ui-btn-sm"
                href={output.publish}
                download="publish.txt"
              >
                {T.publish}
              </a>
            )}
          </div>
          {(output.warnings ?? []).length > 0 && (
            <ul aria-label={T.warnings} className="list-disc pl-5 text-small">
              {(output.warnings ?? []).map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
