import { useMutation } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { api } from '../../api/endpoints';
import type { Thumbnail } from '../../api/types';
import { useDebouncedValue } from '../../hooks/useDebouncedValue';
import { usePostvEditor } from '../../hooks/postvEditor';
import { vi } from '../../i18n/vi';
import { errorMessage } from '../../utils/errors';
import { CoverDrop } from '../CoverDrop';
import { Button } from '../ui/Button';
import { Chip } from '../ui/Chip';
import { Input } from '../ui/Field';

const T = vi.postv.export;
export const THUMB_PREVIEW_DELAY_MS = 600;
const DEFAULT_ACCENT = '#FFD43B';

const FRAMES = [
  {
    key: 'g34',
    label: T.coverPreview34,
    ratio: '3 / 4',
    top: -(240 / 1440) * 100,
    height: (1920 / 1440) * 100,
  },
  {
    key: 'g32',
    label: T.coverPreview32,
    ratio: '3 / 2',
    top: -(600 / 720) * 100,
    height: (1920 / 720) * 100,
  },
] as const;

function usableLines(t: Thumbnail): boolean {
  return t.lines.filter((l) => l.trim() !== '').length >= 1;
}

function PostvCoverPreview({
  slug,
  thumbnail,
  version,
}: {
  slug: string;
  thumbnail: Thumbnail;
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
      .previewPostvThumbnail(slug, draft, controller.signal)
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
    <div aria-label={T.coverPreview} className="space-y-2">
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
      {!usableLines(thumbnail) && (
        <p className="text-small text-muted">{vi.export.thumb.needLines}</p>
      )}
      {error && (
        <p role="alert" className="text-small text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

/**
 * Trình soạn ảnh bìa PostV: chip "Khung gameplay" / "Ảnh tải lên",
 * 2–3 dòng chữ bìa, xem trước 3:4 và 3:2 (PV6).
 */
export function PostvThumbnailEditor() {
  const { project, update, flush } = usePostvEditor();
  const thumb = project.thumbnail;
  const [coverVersion, setCoverVersion] = useState(0);

  const upload = useMutation({
    mutationFn: async (f: File) => {
      await flush();
      return api.uploadAsset(project.slug, 'cover', f);
    },
    onSuccess: (res) => {
      const image = res.project.thumbnail?.image ?? null;
      update((p) => (p.thumbnail ? { ...p, thumbnail: { ...p.thumbnail, image } } : p));
      setCoverVersion((v) => v + 1);
    },
  });

  const patch = (change: Partial<Thumbnail>) =>
    update((p) => (p.thumbnail ? { ...p, thumbnail: { ...p.thumbnail, ...change } } : p));

  const setLine = (index: number, value: string) => {
    if (!thumb) return;
    const all = [0, 1, 2].map((k) => (k === index ? value : (thumb.lines[k] ?? '')));
    patch({ lines: all.filter((line, k) => k < 2 || line.trim() !== '') });
  };

  const defaultLines = project.hook?.text?.trim()
    ? [project.hook.text.trim(), '']
    : ['TIÊU ĐỀ BÀI', 'POSTV'];

  return (
    <section className="space-y-4">
      <h2 className="text-h2 font-bold">{T.cover}</h2>
      <p className="text-small text-muted">{T.coverHelp}</p>

      {!thumb ? (
        <Button
          tone="soft"
          onClick={() =>
            update((p) => ({
              ...p,
              thumbnail: {
                scene: 1,
                lines: defaultLines,
                series: p.series,
                accent: DEFAULT_ACCENT,
              },
            }))
          }
        >
          {vi.export.thumb.add}
        </Button>
      ) : (
        <div className="space-y-4">
          <div className="ui-field">
            <span className="ui-label" id="pv-cover-mode">
              {T.coverMode}
            </span>
            <div className="flex flex-wrap gap-2" role="group" aria-labelledby="pv-cover-mode">
              <Chip small selected={!thumb.image} onClick={() => patch({ image: null })}>
                {T.gameplayFrame}
              </Chip>
              <Chip
                small
                selected={Boolean(thumb.image)}
                onClick={() => {
                  if (!thumb.image) patch({ image: 'images/cover.jpg' });
                }}
              >
                {T.customUpload}
              </Chip>
            </div>
          </div>

          {Boolean(thumb.image) && (
            <div className="space-y-2">
              <CoverDrop
                label={vi.export.thumb.imageDrop}
                busy={upload.isPending}
                onFile={(file) => upload.mutate(file)}
              />
              <div className="flex items-center justify-between">
                <span className="text-small text-muted">{thumb.image}</span>
                <Button tone="soft" size="sm" onClick={() => patch({ image: null })}>
                  {vi.export.thumb.imageRemove}
                </Button>
              </div>
            </div>
          )}

          <div className="grid gap-3">
            {[0, 1, 2].map((i) => (
              <Input
                key={i}
                id={`postv-thumb-line-${i}`}
                label={i < 2 ? T.coverLine(i + 1) : T.coverLineOptional(i + 1)}
                value={thumb.lines[i] ?? ''}
                onChange={(e) => setLine(i, e.target.value)}
              />
            ))}
          </div>

          <div className="grid gap-3 min-[640px]:grid-cols-2">
            <Input
              label={T.coverSeries}
              placeholder={T.coverSeriesPlaceholder}
              value={thumb.series}
              onChange={(e) => patch({ series: e.target.value })}
            />
            <Input
              label={T.coverAccent}
              value={thumb.accent}
              onChange={(e) => patch({ accent: e.target.value })}
            />
          </div>

          <PostvCoverPreview slug={project.slug} thumbnail={thumb} version={coverVersion} />
        </div>
      )}
    </section>
  );
}
