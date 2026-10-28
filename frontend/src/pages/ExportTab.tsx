import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { fetchHealth } from '../api/client';
import { api, projectFileUrl } from '../api/endpoints';
import type { Fps, Job, RenderOptions, RenderRecord } from '../api/types';
import { ChecksCard } from '../components/export/ChecksCard';
import { CleanCard } from '../components/export/CleanCard';
import { HistoryGrid } from '../components/export/HistoryGrid';
import { PublishCard } from '../components/export/PublishCard';
import { ResultCard, type ResultInfo } from '../components/export/ResultCard';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { ErrorNote } from '../components/ErrorNote';
import { AlertIcon, DownloadIcon, PlayIcon, StopIcon } from '../components/icons';
import { ThumbnailEditor } from '../components/ThumbnailEditor';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Chip } from '../components/ui/Chip';
import { Progress } from '../components/ui/Progress';
import { Switch } from '../components/ui/Switch';
import { useProjectEditor } from '../hooks/projectEditor';
import { useRenderJob } from '../hooks/renderJob';
import { useToast } from '../hooks/toast';
import { useLatestCovers } from '../hooks/useCovers';
import { HEAD_PREVIEW_SECONDS, projectFps, useEstimates } from '../hooks/useEstimates';
import { useRemainingText } from '../hooks/useRemaining';
import { vi } from '../i18n/vi';
import { renderBlockers } from '../utils/blockers';
import { formatEstimate, type RenderKind } from '../utils/estimate';

const X = vi.export;
const FPS: Fps[] = [30, 50, 60];
export { HEAD_PREVIEW_SECONDS };

/** Những gì cột phải cần để phát và tải một lần dựng (job vừa xong hoặc dòng lịch sử). */
interface Media {
  key: string;
  video: string;
  srt: string | null;
  cover: string | null;
  youtube_cover: string | null;
  publish: string | null;
}

function jobInfo(job: Job): ResultInfo | null {
  const o = job.output;
  if (!o) return null;
  return {
    duration: o.duration,
    fps: o.fps,
    lufs: o.lufs,
    aligner: o.aligner,
    aligner_info: o.aligner_info,
    trimmed_tail: o.trimmed_tail,
    trimmed_tail_seconds: o.trimmed_tail_seconds,
    seconds: o.seconds,
    warnings: o.warnings,
  };
}

function recordInfo(r: RenderRecord): ResultInfo {
  return {
    duration: r.duration,
    fps: r.fps,
    lufs: r.lufs,
    aligner: r.aligner,
    aligner_info: r.aligner_info,
    trimmed_tail: r.trimmed_tail,
    trimmed_tail_seconds: r.trimmed_tail_seconds,
    seconds: r.render_seconds ?? null,
    warnings: [],
  };
}

function DownloadLink({ href, file, label }: { href: string; file: string; label: string }) {
  return (
    <a className="ui-btn ui-btn-soft ui-btn-sm" href={href} download={file}>
      <DownloadIcon size={18} />
      {label}
    </a>
  );
}

export function ExportTab() {
  const editor = useProjectEditor();
  const toast = useToast();
  const navigate = useNavigate();
  const location = useLocation();
  const { project } = editor;
  const slug = project.slug;
  const outro = project.settings.outro;
  const rj = useRenderJob();
  const remainingText = useRemainingText();
  const estimates = useEstimates(project);
  const covers = useLatestCovers(slug);
  const mine = rj.slug === slug;
  const finished = mine ? rj.finished : null;
  const connectionError = mine ? rj.connectionError : null;
  const [finalFps, setFinalFps] = useState<Fps>(projectFps(project));
  const [played, setPlayed] = useState<RenderRecord | null>(null);
  const [toDelete, setToDelete] = useState<RenderRecord | null>(null);
  // Đang xoá lần xuất này: gỡ `src` của <video> để Windows nhả file.
  const [releasing, setReleasing] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  const health = useQuery({ queryKey: ['health'], queryFn: () => fetchHealth(), retry: false });
  const renders = useQuery({ queryKey: ['renders', slug], queryFn: () => api.listRenders(slug) });
  const lint = useQuery({
    queryKey: ['lint', slug, editor.savedCount],
    queryFn: () => api.lint(slug),
    retry: false,
  });

  const queryClient = useQueryClient();
  const remove = useMutation({
    mutationFn: async (r: RenderRecord) => {
      const el = videoRef.current;
      if (el) {
        el.pause();
        el.removeAttribute('src');
        el.load(); // nhả file đang mở trước khi xoá
      }
      setReleasing(r.job_id);
      await api.deleteRender(slug, r.job_id);
    },
    onSuccess: (_d, r) => {
      toast.info(X.history.deleted);
      setToDelete(null);
      setReleasing(null);
      if (played?.job_id === r.job_id) setPlayed(null);
      void queryClient.invalidateQueries({ queryKey: ['renders', slug] });
      void queryClient.invalidateQueries({ queryKey: ['projects'] });
    },
    onError: (e) => {
      setToDelete(null);
      setReleasing(null); // 409 (đang dựng / file đang mở): trả lại video cho trình phát
      toast.error(e);
    },
  });

  const missing = useMemo(() => renderBlockers(project), [project]);
  const blocked = !!lint.data && (lint.data.blocked || lint.data.problems.length > 0);
  const noFfmpeg = health.data?.ffmpeg === false;
  const reason =
    missing.length > 0
      ? missing.join(' · ')
      : blocked
        ? X.blocked
        : noFfmpeg
          ? X.missingFfmpeg
          : undefined;

  const start = useMutation({
    mutationFn: async ({ options, kind }: { options: RenderOptions; kind: RenderKind }) => {
      await editor.flush();
      await rj.start(slug, { ...options, outro }, estimates.estimate(kind));
    },
    onSuccess: () => setPlayed(null),
    onError: (e, vars) => toast.error(e, () => start.mutate(vars)),
  });

  const headKind: RenderKind = { kind: 'head', seconds: HEAD_PREVIEW_SECONDS };
  const launchHead = () =>
    start.mutate({
      options: { preview: true, preview_seconds: HEAD_PREVIEW_SECONDS },
      kind: headKind,
    });

  const running = rj.running;
  const cannotStart = running || start.isPending || !!reason;

  // Xem nhanh tự dựng một lần khi mở tab từ nút Xem nhanh ở Soạn video / Âm thanh. Chờ kiểm tra
  // và môi trường xong; thiếu nguyên liệu hoặc bị chặn thì không dựng (thẻ Kiểm tra đã hiện lý do).
  const auto = (location.state as { auto?: string } | null)?.auto;
  const autoHandled = useRef(false);
  useEffect(() => {
    if (auto !== 'preview' || autoHandled.current) return;
    if (lint.isPending || health.isPending) return;
    autoHandled.current = true;
    navigate(location.pathname, { replace: true, state: null });
    if (lint.isError || cannotStart) return;
    launchHead();
    // Chỉ chạy lại khi dữ liệu kiểm tra về; launchHead đổi mỗi lần vẽ.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auto, lint.isPending, health.isPending]);

  const failure = finished?.status === 'failed' ? finished : null;
  const history = renders.data ?? [];
  const firstImage = project.scenes[0]?.image;
  const fallbackImage = firstImage ? projectFileUrl(slug, firstImage) : null;

  // Đang xem: dòng lịch sử được chọn, không thì job vừa xong của dự án này, không thì lần xuất mới
  // nhất trong lịch sử (nên tải lại trang vẫn còn trình phát và nút tải).
  const out = finished?.status === 'done' ? finished.output : null;
  const shown = played?.video ? played : !out ? (history.find((r) => r.video) ?? null) : null;
  const media: Media | null = shown?.video
    ? {
        key: shown.job_id,
        video: shown.video,
        srt: shown.srt,
        cover: shown.cover,
        youtube_cover: shown.youtube_cover,
        publish: shown.publish,
      }
    : out && finished
      ? {
          key: finished.id,
          video: out.video,
          srt: out.srt,
          cover: out.cover,
          youtube_cover: out.youtube_cover,
          publish: out.publish,
        }
      : null;
  const info = shown ? recordInfo(shown) : finished ? jobInfo(finished) : null;
  const currentId = shown?.job_id ?? (finished?.status === 'done' ? finished.id : null);

  const pct = finished?.progress ?? (mine ? rj.percent : 0);
  const stepName = finished?.step ?? (mine ? rj.step : '');
  const finalKind: RenderKind = { kind: 'final', fps: finalFps };
  const idleEstimate = (kind: RenderKind) => formatEstimate(estimates.estimate(kind));

  return (
    <div className="grid grid-cols-1 gap-[18px] p-6 min-[1024px]:grid-cols-[minmax(0,1fr)_300px]">
      <div className="min-w-0 space-y-[18px]">
        <h1 className="text-h1 font-extrabold uppercase">{X.title}</h1>
        <ChecksCard slug={slug} lint={lint} missing={missing} />

        {info && <ResultCard info={info} />}
        {media?.publish && <PublishCard url={media.publish} />}

        <Card as="section" aria-label={X.thumb.title}>
          <ThumbnailEditor covers={covers} />
        </Card>

        <HistoryGrid
          renders={history}
          fallbackImage={fallbackImage}
          current={currentId}
          onSelect={setPlayed}
          lockedId={running && mine ? rj.jobId : null}
          onDelete={setToDelete}
        />

        <CleanCard slug={slug} disabled={running} />
      </div>

      <aside
        aria-label={X.title}
        className="space-y-4 self-start min-[1024px]:sticky min-[1024px]:top-6"
      >
        <Card as="section" className="space-y-4">
          <div role="group" aria-label={X.fpsGroup} className="flex items-center gap-2">
            <span className="ui-label !mb-0 mr-1">{X.fpsGroup}</span>
            {FPS.map((f) => (
              <Chip key={f} small selected={finalFps === f} onClick={() => setFinalFps(f)}>
                {f}
              </Chip>
            ))}
          </div>
          <div className="flex items-center justify-between gap-3">
            <span className="font-bold">{X.options.outro}</span>
            <Switch
              checked={outro}
              label={X.outroLabel}
              onChange={(checked) =>
                editor.update((p) => ({ ...p, settings: { ...p.settings, outro: checked } }))
              }
            />
          </div>
          <div className="space-y-2">
            <Button
              tone="ink"
              size="lg"
              className="w-full"
              busy={start.isPending}
              disabled={cannotStart}
              reason={reason}
              icon={<PlayIcon size={20} />}
              onClick={launchHead}
            >
              {X.fast}
            </Button>
            <Button
              tone="accent"
              size="lg"
              className="w-full"
              disabled={cannotStart}
              reason={reason}
              onClick={() =>
                start.mutate({ options: { preview: false, fps: finalFps }, kind: finalKind })
              }
            >
              {X.finalLabel(finalFps)}
            </Button>
          </div>
          {media && (
            <div
              role="group"
              aria-label={X.downloads}
              data-slot="downloads"
              className="flex flex-wrap gap-2"
            >
              <DownloadLink href={media.video} file="video.mp4" label={X.result.video} />
            </div>
          )}
          {reason && (
            <p className="flex items-center gap-2 text-small font-bold text-danger">
              <AlertIcon size={18} />
              {reason}
            </p>
          )}
          <p
            data-slot="estimate"
            className="min-h-5 text-center text-small tabular-nums text-muted"
          >
            {running && mine
              ? remainingText
              : estimates.loaded
                ? vi.estimate.line(idleEstimate(headKind), idleEstimate(finalKind), finalFps)
                : ''}
          </p>
        </Card>

        {(running || finished || connectionError) && mine && (
          <Card as="section" aria-label={X.progress} aria-live="polite" className="space-y-3">
            <Progress value={pct} label={X.progress} />
            <p className="text-small">
              <span className="tabular-nums">{Math.round(pct)}%</span>
              {stepName && <span> · {stepName}</span>}
              {running && rj.message && <span className="text-muted"> — {rj.message}</span>}
            </p>
            {running && (
              <div className="flex items-center justify-between gap-2 text-small text-muted">
                <span className="tabular-nums">{remainingText}</span>
                <Button
                  tone="soft"
                  size="sm"
                  icon={<StopIcon size={18} />}
                  onClick={() => void rj.cancel()}
                >
                  {X.cancel}
                </Button>
              </div>
            )}
            <ErrorNote error={connectionError} />
            {finished?.status === 'cancelled' && <p className="text-small">{X.cancelled}</p>}
            {failure && (
              <div className="space-y-3 rounded-inner border-[1.5px] border-danger p-4">
                <p role="alert" className="flex items-center gap-2 font-bold text-danger">
                  <AlertIcon size={18} />
                  {X.failed}: {failure.error}
                </p>
                {failure.needs_confirmation && (
                  <>
                    <p className="text-small">{X.confirmTrim}</p>
                    {failure.cut_audio && (
                      <audio controls aria-label={X.cutAudio} src={failure.cut_audio} />
                    )}
                    <Button
                      tone="ink"
                      size="sm"
                      onClick={() =>
                        start.mutate({
                          options: { ...rj.options, allow_long_trim: true },
                          kind: rj.options.preview
                            ? headKind
                            : { kind: 'final', fps: rj.options.fps ?? finalFps },
                        })
                      }
                    >
                      {X.confirmTrimButton}
                    </Button>
                  </>
                )}
              </div>
            )}
          </Card>
        )}

        <Card as="section" className="space-y-3">
          {media ? (
            <div className="ui-frame mx-auto overflow-hidden bg-black">
              <video
                ref={videoRef}
                key={media.key}
                controls
                aria-label={X.player}
                className="h-full w-full bg-black object-contain"
                src={releasing === media.key ? undefined : media.video}
              />
            </div>
          ) : (
            <p className="text-small text-muted">{X.noPlayer}</p>
          )}
        </Card>
      </aside>
      {toDelete && (
        <ConfirmDialog
          title={X.history.deleteTitle}
          message={X.history.deleteBody}
          confirmLabel={X.history.remove}
          danger
          busy={remove.isPending}
          onConfirm={() => remove.mutate(toDelete)}
          onCancel={() => !remove.isPending && setToDelete(null)}
        />
      )}
    </div>
  );
}
