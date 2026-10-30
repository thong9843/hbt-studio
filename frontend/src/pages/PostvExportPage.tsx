import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import { api } from '../api/endpoints';
import type { Fps, RenderRecord } from '../api/types';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { HistoryGrid } from '../components/export/HistoryGrid';
import { PublishCard } from '../components/export/PublishCard';
import { PostvRenderPanel } from '../components/postv/PostvRenderPanel';
import { PostvThumbnailEditor } from '../components/postv/PostvThumbnailEditor';
import { useToast } from '../hooks/toast';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Chip } from '../components/ui/Chip';
import { Switch } from '../components/ui/Switch';
import { usePostvEditor } from '../hooks/postvEditor';
import { useRenderJob } from '../hooks/renderJob';
import { vi } from '../i18n/vi';

const T = vi.postv.export;
const FPS: Fps[] = [30, 50, 60];

interface Media {
  key: string;
  video: string;
  publish: string | null;
}

/**
 * Bước 5 · Xuất: chọn fps, outro, dựng bản đẹp, ảnh bìa (gameplay / tải lên),
 * nội dung đăng (có dòng nguồn), lịch sử lần xuất và dọn file tạm (PV6).
 */
export function PostvExportPage() {
  const { project, update } = usePostvEditor();
  const toast = useToast();
  const queryClient = useQueryClient();
  const rj = useRenderJob();
  const videoRef = useRef<HTMLVideoElement>(null);

  const [played, setPlayed] = useState<RenderRecord | null>(null);
  const [toDelete, setToDelete] = useState<RenderRecord | null>(null);
  const [releasing, setReleasing] = useState<string | null>(null);

  const fps = project.settings.fps as Fps;
  const ready =
    project.post.text.trim() !== '' &&
    project.segments.some((s) => s.voice.trim() !== '') &&
    Boolean(project.voice.file);

  const renders = useQuery({
    queryKey: ['renders', project.slug],
    queryFn: () => api.listRenders(project.slug),
  });

  const remove = useMutation({
    mutationFn: async (r: RenderRecord) => {
      const el = videoRef.current;
      if (el) {
        el.pause();
        el.removeAttribute('src');
        el.load();
      }
      setReleasing(r.job_id);
      await api.deleteRender(project.slug, r.job_id);
    },
    onSuccess: (_d, r) => {
      toast.info(vi.export.history.deleted);
      setToDelete(null);
      setReleasing(null);
      if (played?.job_id === r.job_id) setPlayed(null);
      void queryClient.invalidateQueries({ queryKey: ['renders', project.slug] });
      void queryClient.invalidateQueries({ queryKey: ['projects'] });
    },
    onError: (e) => {
      setToDelete(null);
      setReleasing(null);
      toast.error(e);
    },
  });

  const cleanMutation = useMutation({
    mutationFn: () => api.cleanBuild(project.slug),
    onSuccess: () => toast.info(T.cleanDone),
    onError: (e) => toast.error(e),
  });

  const history = renders.data ?? [];
  const mine = rj.slug === project.slug;
  const running = mine && rj.running;
  const finished = mine ? rj.finished : null;
  const out = finished?.status === 'done' ? finished.output : null;

  const shown = played?.video ? played : !out ? (history.find((r) => r.video) ?? null) : null;
  const media: Media | null = shown?.video
    ? {
        key: shown.job_id,
        video: shown.video,
        publish: shown.publish,
      }
    : out?.video
      ? {
          key: finished?.id ?? 'output',
          video: out.video,
          publish: out.publish,
        }
      : null;

  const currentId = played?.job_id ?? shown?.job_id ?? null;
  const fallbackImage = project.background?.clip_ids?.[0]
    ? api.backgroundThumbUrl(project.background.clip_ids[0])
    : null;

  const sourceVal = (project.source?.url || project.source?.note || '').trim();
  const sourceLineText = sourceVal ? `Nguồn: ${sourceVal}` : '';
  const hashtags = project.publish?.hashtags ?? [];

  return (
    <div className="grid gap-6 min-[1024px]:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
      <div className="space-y-6">
        <Card as="section" aria-label={T.cover}>
          <PostvThumbnailEditor />
        </Card>

        {media?.publish ? (
          <PublishCard url={media.publish} />
        ) : (
          <Card as="section" aria-label={T.publishContent} className="space-y-3">
            <h2 className="text-h2 font-bold">{T.publishContent}</h2>
            <div className="space-y-2 rounded-inner bg-soft p-3 text-small">
              <p className="font-bold text-muted">[TikTok]</p>
              <p>{project.publish?.hook || project.post?.text || '...'}</p>
              {sourceLineText && <p className="font-semibold">{sourceLineText}</p>}
              {hashtags.length > 0 && (
                <p className="text-muted">
                  {hashtags.map((h) => (h.startsWith('#') ? h : `#${h}`)).join(' ')}
                </p>
              )}
            </div>
          </Card>
        )}

        <HistoryGrid
          renders={history}
          fallbackImage={fallbackImage}
          current={currentId}
          onSelect={setPlayed}
          lockedId={running && mine ? rj.jobId : null}
          onDelete={setToDelete}
        />

        <div className="flex items-center justify-between gap-3 pt-2">
          <Button
            tone="soft"
            size="sm"
            disabled={running || cleanMutation.isPending}
            onClick={() => cleanMutation.mutate()}
          >
            {T.cleanBuild}
          </Button>
        </div>
      </div>

      <aside
        aria-label={T.title}
        className="space-y-4 self-start min-[1024px]:sticky min-[1024px]:top-6"
      >
        <Card as="section" className="space-y-4">
          <h2 className="text-h2 font-bold">{T.title}</h2>
          <p className="text-small text-muted">{T.help}</p>
          <div className="ui-field">
            <span className="ui-label" id="pv-fps-label">
              {T.fps}
            </span>
            <div className="flex flex-wrap gap-2" role="group" aria-labelledby="pv-fps-label">
              {FPS.map((value) => (
                <Chip
                  key={value}
                  selected={fps === value}
                  onClick={() => update((p) => ({ ...p, settings: { ...p.settings, fps: value } }))}
                >
                  {`${value} fps`}
                </Chip>
              ))}
            </div>
          </div>
          <Switch
            label={T.outro}
            checked={project.settings.outro}
            onChange={(checked) =>
              update((p) => ({ ...p, settings: { ...p.settings, outro: checked } }))
            }
          />
          <PostvRenderPanel
            label={T.final(fps)}
            tone="accent"
            options={{ preview: false, fps, outro: project.settings.outro }}
            blocked={ready ? null : T.notReady}
          />
        </Card>

        {media && (
          <Card as="section" className="space-y-3">
            <div className="ui-frame mx-auto overflow-hidden bg-black">
              <video
                ref={videoRef}
                key={media.key}
                controls
                aria-label={vi.postv.render.player}
                className="h-full w-full bg-black object-contain"
                src={releasing === media.key ? undefined : media.video}
              />
            </div>
          </Card>
        )}
      </aside>

      {toDelete && (
        <ConfirmDialog
          title={T.deleteRenderTitle}
          message={T.deleteRenderBody}
          confirmLabel={T.remove}
          danger
          busy={remove.isPending}
          onConfirm={() => void remove.mutate(toDelete)}
          onCancel={() => setToDelete(null)}
        />
      )}
    </div>
  );
}
