import { useEffect, useRef, useState } from 'react';
import { api } from '../api/endpoints';
import type { Thumbnail } from '../api/types';
import { useDebouncedValue } from '../hooks/useDebouncedValue';
import { useProjectEditor } from '../hooks/projectEditor';
import { vi } from '../i18n/vi';
import { errorMessage } from '../utils/errors';
import { sceneNumber } from '../utils/scene';
import { DownloadIcon } from './icons';

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

function CoverPreview({ slug, thumbnail }: { slug: string; thumbnail: Thumbnail }) {
  const key = JSON.stringify(thumbnail);
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
    const draft = JSON.parse(settled) as Thumbnail;
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
              className="relative w-[180px] overflow-hidden rounded-frame bg-surface"
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
            <figcaption className="text-small text-text-muted">{f.label}</figcaption>
          </figure>
        ))}
      </div>
      {!usableLines(thumbnail) && <p className="text-small text-text-muted">{T.needLines}</p>}
      {error && (
        <p role="alert" className="text-small text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

export function ThumbnailEditor({ covers }: { covers: { cover: string; youtube: string } | null }) {
  const editor = useProjectEditor();
  const { project } = editor;
  const thumb = project.thumbnail;

  const patch = (change: Partial<Thumbnail>) =>
    editor.update((p) => (p.thumbnail ? { ...p, thumbnail: { ...p.thumbnail, ...change } } : p));

  const setLine = (index: number, value: string) => {
    if (!thumb) return;
    const all = [0, 1, 2].map((k) => (k === index ? value : (thumb.lines[k] ?? '')));
    patch({ lines: all.filter((line, k) => k < 2 || line.trim() !== '') });
  };

  return (
    <section className="space-y-4">
      <h2>{T.title}</h2>
      <p className="text-small text-text-muted">{T.help}</p>
      {!thumb ? (
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() =>
            editor.update((p) => ({
              ...p,
              thumbnail: { scene: 1, lines: ['', ''], series: '', accent: DEFAULT_ACCENT },
            }))
          }
        >
          {T.add}
        </button>
      ) : (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <div key={i}>
                <label className="label" htmlFor={`thumb-line-${i}`}>
                  {i < 2 ? T.line(i + 1) : T.lineOptional(i + 1)}
                </label>
                <input
                  id={`thumb-line-${i}`}
                  className="input"
                  value={thumb.lines[i] ?? ''}
                  onChange={(e) => setLine(i, e.target.value)}
                />
              </div>
            ))}
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <div>
              <label className="label" htmlFor="thumb-scene">
                {T.scene}
              </label>
              <select
                id="thumb-scene"
                className="input"
                value={thumb.scene}
                onChange={(e) => patch({ scene: Number(e.target.value) })}
              >
                {project.scenes.map((_, i) => (
                  <option key={i} value={sceneNumber(i)}>
                    {T.sceneOption(sceneNumber(i))}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label" htmlFor="thumb-series">
                {T.series}
              </label>
              <input
                id="thumb-series"
                className="input"
                placeholder={project.series}
                value={thumb.series}
                onChange={(e) => patch({ series: e.target.value })}
              />
            </div>
            <div>
              <label className="label" htmlFor="thumb-accent">
                {T.accent}
              </label>
              <input
                id="thumb-accent"
                type="color"
                className="input h-11 w-24 p-1"
                value={thumb.accent}
                onChange={(e) => patch({ accent: e.target.value.toUpperCase() })}
              />
            </div>
          </div>
          <CoverPreview slug={project.slug} thumbnail={thumb} />
          <div className="flex flex-wrap items-center gap-3">
            {covers ? (
              <>
                <a className="btn btn-secondary" href={covers.cover} download="cover_9x16.jpg">
                  <DownloadIcon size={20} />
                  {T.download916}
                </a>
                <a className="btn btn-secondary" href={covers.youtube} download="youtube_3x2.jpg">
                  <DownloadIcon size={20} />
                  {T.download32}
                </a>
              </>
            ) : (
              <p className="text-small text-text-muted">{T.noFilesYet}</p>
            )}
            <button
              type="button"
              className="btn btn-outline btn-sm ml-auto"
              onClick={() => editor.update((p) => ({ ...p, thumbnail: null }))}
            >
              {T.remove}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
