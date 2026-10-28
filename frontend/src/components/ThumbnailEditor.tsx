import { useMutation } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { api, projectFileUrl } from '../api/endpoints';
import type { Thumbnail } from '../api/types';
import { useDebouncedValue } from '../hooks/useDebouncedValue';
import { useProjectEditor } from '../hooks/projectEditor';
import { vi } from '../i18n/vi';
import { errorMessage } from '../utils/errors';
import { sceneNumber } from '../utils/scene';
import { CoverDrop } from './CoverDrop';
import { ErrorNote } from './ErrorNote';
import { DownloadIcon } from './icons';
import { Button } from './ui/Button';
import { Chip } from './ui/Chip';
import { Input } from './ui/Field';

const T = vi.export.thumb;
export const THUMB_PREVIEW_DELAY_MS = 600;
const DEFAULT_ACCENT = '#FFD43B';

/** Hai khung cắt từ ảnh bìa 9:16 (1080×1920): 3:4 là y=240..1680, 3:2 là y=600..1320. */
const FRAMES = [
  {
    key: 'g34',
    label: T.frame34,
    ratio: '3 / 4',
    top: -(240 / 1440) * 100,
    height: (1920 / 1440) * 100,
  },
  {
    key: 'g32',
    label: T.frame32,
    ratio: '3 / 2',
    top: -(600 / 720) * 100,
    height: (1920 / 720) * 100,
  },
] as const;

function usableLines(t: Thumbnail): boolean {
  return t.lines.filter((l) => l.trim() !== '').length >= 2;
}

function CoverPreview({
  slug,
  thumbnail,
  version,
}: {
  slug: string;
  thumbnail: Thumbnail;
  /** Tăng sau mỗi lần tải ảnh bìa mới (tên file không đổi nên khoá JSON không đổi). */
  version: number;
}) {
  const key = JSON.stringify({ thumbnail, version });
  const settled = useDebouncedValue(key, THUMB_PREVIEW_DELAY_MS);
  const [url, setUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const urlRef = useRef<string | null>(null);

  useEffect(
    () => () => {
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    },
    [],
  );

  useEffect(() => {
    const draft = (JSON.parse(settled) as { thumbnail: Thumbnail }).thumbnail;
    if (!usableLines(draft)) return;
    const controller = new AbortController();
    setLoading(true);
    api
      .previewThumbnail(slug, draft, controller.signal)
      .then((blob) => {
        if (controller.signal.aborted) return;
        if (urlRef.current) URL.revokeObjectURL(urlRef.current);
        urlRef.current = URL.createObjectURL(blob);
        setUrl(urlRef.current);
        setError(null);
      })
      .catch((e: unknown) => {
        if (!controller.signal.aborted) setError(errorMessage(e));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [settled, slug]);

  const stale = key !== settled || loading;
  return (
    <div aria-label={T.previewTitle} className="space-y-2">
      <div className="flex flex-wrap gap-4">
        {FRAMES.map((f) => (
          <figure key={f.key} className="space-y-1">
            <div
              className="relative w-[180px] overflow-hidden rounded-inner bg-soft"
              style={{ aspectRatio: f.ratio, opacity: stale ? 0.6 : 1 }}
            >
              {url && (
                <img
                  src={url}
                  alt={f.label}
                  className="absolute left-0 w-full max-w-none"
                  style={{ top: `${f.top}%`, height: `${f.height}%` }}
                />
              )}
            </div>
            <figcaption className="text-small text-muted">{f.label}</figcaption>
          </figure>
        ))}
      </div>
      {!usableLines(thumbnail) && <p className="text-small text-muted">{T.needLines}</p>}
      {error && (
        <p role="alert" className="text-small text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

/**
 * Ảnh bìa: 2–3 dòng, cảnh nền, chữ series, màu dòng cuối, xem trước 3:4 và 3:2.
 * `covers` có thì hiện nút tải file từ lần xuất gần nhất; bỏ qua (`undefined`) thì không hiện
 * (ngăn kéo "Bìa & đăng" ở Soạn video không đọc lịch sử dựng).
 */
export function ThumbnailEditor({
  covers,
}: {
  covers?: { cover: string; youtube: string } | null;
}) {
  const editor = useProjectEditor();
  const { project } = editor;
  const thumb = project.thumbnail;
  const [coverVersion, setCoverVersion] = useState(0);
  const upload = useMutation({
    mutationFn: async (f: File) => {
      await editor.flush(); // máy chủ chỉ nhận ảnh bìa khi khối thumbnail đã được lưu
      return api.uploadAsset(project.slug, 'cover', f);
    },
    onSuccess: (res) => {
      const image = res.project.thumbnail?.image ?? null;
      editor.applyServer((p) => (p.thumbnail ? { ...p, thumbnail: { ...p.thumbnail, image } } : p));
      setCoverVersion((v) => v + 1);
    },
  });

  const patch = (change: Partial<Thumbnail>) =>
    editor.update((p) => (p.thumbnail ? { ...p, thumbnail: { ...p.thumbnail, ...change } } : p));

  const setLine = (index: number, value: string) => {
    if (!thumb) return;
    const all = [0, 1, 2].map((k) => (k === index ? value : (thumb.lines[k] ?? '')));
    patch({ lines: all.filter((line, k) => k < 2 || line.trim() !== '') });
  };

  return (
    <section className="space-y-4">
      <h2 className="text-h2 font-bold">{T.title}</h2>
      <p className="text-small text-muted">{T.help}</p>
      {!thumb ? (
        <Button
          tone="soft"
          onClick={() =>
            editor.update((p) => ({
              ...p,
              thumbnail: { scene: 1, lines: ['', ''], series: '', accent: DEFAULT_ACCENT },
            }))
          }
        >
          {T.add}
        </Button>
      ) : (
        <div className="space-y-4">
          <div className="grid gap-3">
            {[0, 1, 2].map((i) => (
              <Input
                key={i}
                id={`thumb-line-${i}`}
                label={i < 2 ? T.line(i + 1) : T.lineOptional(i + 1)}
                value={thumb.lines[i] ?? ''}
                onChange={(e) => setLine(i, e.target.value)}
              />
            ))}
          </div>
          <div className="space-y-2">
            <p className="ui-label !mb-0" id="thumb-scene">
              {T.scene}
            </p>
            <div role="group" aria-labelledby="thumb-scene" className="flex flex-wrap gap-2">
              {project.scenes.map((_, i) => (
                <Chip
                  key={i}
                  small
                  disabled={!!thumb.image}
                  selected={thumb.scene === sceneNumber(i)}
                  onClick={() => patch({ scene: sceneNumber(i) })}
                >
                  {T.sceneOption(sceneNumber(i))}
                </Chip>
              ))}
            </div>
            {thumb.image && <p className="text-small text-muted">{T.sceneOff}</p>}
          </div>
          <div className="space-y-2">
            <p className="ui-label !mb-0">{T.image}</p>
            {thumb.image && (
              <div className="ui-inner flex items-center gap-3 p-3">
                <img
                  src={`${projectFileUrl(project.slug, thumb.image)}?v=${coverVersion}`}
                  alt={T.imageAlt}
                  loading="lazy"
                  decoding="async"
                  className="h-24 w-[54px] shrink-0 rounded-[10px] object-cover"
                />
                <p className="min-w-0 flex-1 text-small font-bold">{T.imageUsing}</p>
                <Button tone="ghost" size="sm" onClick={() => patch({ image: null })}>
                  {T.imageRemove}
                </Button>
              </div>
            )}
            <CoverDrop
              label={thumb.image ? T.imageReplace : T.imageDrop}
              busy={upload.isPending}
              onFile={(f) => upload.mutate(f)}
            />
            <p className="text-small text-muted">{T.imageHelp}</p>
            <ErrorNote error={upload.error} />
          </div>
          <div className="grid grid-cols-[1fr_auto] items-end gap-3">
            <Input
              id="thumb-series"
              label={T.series}
              placeholder={project.series}
              value={thumb.series}
              onChange={(e) => patch({ series: e.target.value })}
            />
            <Input
              id="thumb-accent"
              type="color"
              label={T.accent}
              className="!w-24 !p-1"
              value={thumb.accent}
              onChange={(e) => patch({ accent: e.target.value.toUpperCase() })}
            />
          </div>
          <CoverPreview slug={project.slug} thumbnail={thumb} version={coverVersion} />
          <div className="flex flex-wrap items-center gap-3">
            {covers === undefined ? null : covers ? (
              <>
                <a className="ui-btn ui-btn-soft" href={covers.cover} download="cover_9x16.jpg">
                  <DownloadIcon size={20} />
                  {T.download916}
                </a>
                <a className="ui-btn ui-btn-soft" href={covers.youtube} download="youtube_3x2.jpg">
                  <DownloadIcon size={20} />
                  {T.download32}
                </a>
              </>
            ) : (
              <p className="text-small text-muted">{T.noFilesYet}</p>
            )}
            <Button
              tone="ghost"
              size="sm"
              className="ml-auto"
              onClick={() => editor.update((p) => ({ ...p, thumbnail: null }))}
            >
              {T.remove}
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}
