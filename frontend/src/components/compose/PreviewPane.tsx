import { useEffect, useRef, useState } from 'react';
import { api } from '../../api/endpoints';
import type { Scene, Theme } from '../../api/types';
import { useDebouncedValue } from '../../hooks/useDebouncedValue';
import { vi } from '../../i18n/vi';
import { errorMessage } from '../../utils/errors';
import { safeZoneBands } from '../../utils/safeZone';
import { sceneNumber } from '../../utils/scene';
import { ArrowLeftIcon, EyeIcon } from '../icons';
import { Button } from '../ui/Button';
import { Chip } from '../ui/Chip';
import { IconButton } from '../ui/IconButton';

const T = vi.compose.preview;
export const PREVIEW_DELAY_MS = 600;

interface Props {
  slug: string;
  sceneIndex: number;
  sceneCount: number;
  scene: Scene;
  theme: Theme;
  imageVersion: number;
  /** Lý do chưa dựng được (nút chính tắt); `undefined` = bấm được. */
  blockedReason?: string;
  onPrev: () => void;
  onNext: () => void;
  /** Chuyển sang tab Xuất video (Đợt 3b không tự dựng). */
  onGoExport: () => void;
}

/**
 * Cột 3: hai nút chính, chỗ cho dòng ước tính (Đợt 3d), khung 9:16 xem trước vẽ lại 600 ms sau khi
 * ngừng gõ (huỷ yêu cầu cũ), nút Vùng an toàn và ‹ n/N ›.
 */
export function PreviewPane({
  slug,
  sceneIndex,
  sceneCount,
  scene,
  theme,
  imageVersion,
  blockedReason,
  onPrev,
  onNext,
  onGoExport,
}: Props) {
  const key = JSON.stringify({ scene, theme, imageVersion });
  const settled = useDebouncedValue(key, PREVIEW_DELAY_MS);
  const [url, setUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [safe, setSafe] = useState(false);
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
  const bands = safeZoneBands();
  const off = blockedReason !== undefined;
  return (
    <section aria-label={T.title} className="space-y-4">
      <div className="space-y-2">
        <Button
          tone="ink"
          size="lg"
          className="w-full"
          disabled={off}
          reason={blockedReason}
          onClick={onGoExport}
        >
          {T.fast}
        </Button>
        <Button
          tone="accent"
          size="lg"
          className="w-full"
          disabled={off}
          reason={blockedReason}
          onClick={onGoExport}
        >
          {T.final}
        </Button>
        {/* Chỗ cho dòng ước tính thời gian dựng (Đợt 3d). */}
        <p
          data-slot="estimate"
          className="min-h-5 text-center text-small tabular-nums text-muted"
        />
      </div>

      <div className="ui-frame mx-auto">
        {url && (
          <img
            src={url}
            alt={T.alt(sceneNumber(sceneIndex))}
            className="h-full w-full object-cover transition-opacity duration-[150ms]"
            style={{ opacity: stale ? 0.6 : 1 }}
          />
        )}
        {safe && (
          <div data-testid="safe-zone" aria-hidden="true" className="absolute inset-0">
            <div className="ui-safe ui-safe-top" style={{ height: `${bands.top}%` }} />
            <div className="ui-safe ui-safe-bottom" style={{ height: `${bands.bottom}%` }} />
            <div
              className="ui-safe ui-safe-right"
              style={{ top: `${bands.top}%`, bottom: `${bands.bottom}%`, width: `${bands.right}%` }}
            />
          </div>
        )}
        {stale && !error && (
          <span
            role="status"
            className="absolute right-3 top-3 flex items-center gap-2 rounded-full bg-primary px-3 py-1.5 text-tiny font-semibold text-on-primary"
          >
            <span className="ui-spinner !h-4 !w-4" aria-hidden="true" />
            {T.loading}
          </span>
        )}
        {error && (
          <p
            role="alert"
            className="absolute inset-x-3 bottom-3 rounded-input bg-card p-3 text-small font-bold text-danger"
          >
            {T.error}: {error}
          </p>
        )}
      </div>

      <div className="flex items-center justify-between gap-2">
        <Chip small selected={safe} title={T.safeZoneTitle} onClick={() => setSafe((v) => !v)}>
          <EyeIcon size={16} />
          {T.safeZone}
        </Chip>
        <div className="flex items-center gap-1">
          <IconButton label={T.prev} small disabled={sceneIndex <= 0} onClick={onPrev}>
            <ArrowLeftIcon size={18} />
          </IconButton>
          <span className="min-w-[3rem] text-center text-small font-bold tabular-nums">
            {T.position(sceneNumber(sceneIndex), sceneCount)}
          </span>
          <IconButton label={T.next} small disabled={sceneIndex >= sceneCount - 1} onClick={onNext}>
            <ArrowLeftIcon size={18} className="rotate-180" />
          </IconButton>
        </div>
      </div>
      <p className="text-center text-small text-muted">{T.hint}</p>
    </section>
  );
}
