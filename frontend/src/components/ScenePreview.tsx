import { useEffect, useRef, useState } from 'react';
import { api } from '../api/endpoints';
import type { Scene, Theme } from '../api/types';
import { useDebouncedValue } from '../hooks/useDebouncedValue';
import { vi } from '../i18n/vi';
import { errorMessage } from '../utils/errors';
import { sceneNumber } from '../utils/scene';

export const PREVIEW_DELAY_MS = 600;

interface Props {
  slug: string;
  sceneIndex: number;
  scene: Scene;
  theme: Theme;
  imageVersion: number;
}

/** Ảnh xem trước cảnh: vẽ lại 600 ms sau khi ngừng gõ, bằng đúng bộ vẽ của video. */
export function ScenePreview({ slug, sceneIndex, scene, theme, imageVersion }: Props) {
  const key = JSON.stringify({ scene, theme, imageVersion });
  const settled = useDebouncedValue(key, PREVIEW_DELAY_MS);
  const [url, setUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const urlRef = useRef<string | null>(null);

  useEffect(
    () => () => {
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    },
    [],
  );

  useEffect(() => {
    const payload = JSON.parse(settled) as { scene: Scene; theme: Theme };
    const controller = new AbortController();
    setLoading(true);
    api
      .previewScene(slug, sceneIndex, payload.scene, payload.theme, controller.signal)
      .then((blob) => {
        if (controller.signal.aborted) return;
        if (urlRef.current) URL.revokeObjectURL(urlRef.current);
        urlRef.current = URL.createObjectURL(blob);
        setUrl(urlRef.current);
        setError(null);
      })
      .catch((e: unknown) => {
        if (controller.signal.aborted) return;
        setError(errorMessage(e));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [settled, slug, sceneIndex]);

  const stale = key !== settled || loading;
  return (
    <section aria-label={vi.compose.preview.title}>
      <h2 className="mb-3 text-tiny font-semibold uppercase text-text-muted">
        {vi.compose.preview.title}
      </h2>
      <div className="relative mx-auto aspect-[9/16] w-full max-w-[360px] overflow-hidden rounded-frame bg-surface">
        {url && (
          <img
            src={url}
            alt={vi.compose.preview.alt(sceneNumber(sceneIndex))}
            className={`h-full w-full object-cover transition-opacity duration-[180ms] ${stale ? 'opacity-60' : ''}`}
          />
        )}
        {stale && !error && (
          <span
            role="status"
            className="absolute right-3 top-3 flex items-center gap-2 rounded-full bg-primary px-3 py-1.5 text-tiny font-semibold uppercase text-on-primary"
          >
            <span className="spinner h-4 w-4" aria-hidden="true" />
            {vi.compose.preview.loading}
          </span>
        )}
        {error && (
          <p
            role="alert"
            className="absolute inset-x-3 bottom-3 rounded-input bg-bg p-3 text-small font-bold text-danger"
          >
            {vi.compose.preview.error}: {error}
          </p>
        )}
      </div>
      <p className="mt-3 text-center text-small text-text-muted">{vi.compose.preview.hint}</p>
    </section>
  );
}
