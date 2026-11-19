import type { ReactNode } from 'react';
import { vi } from '../../i18n/vi';
import { EyeIcon, GripIcon, PlayIcon } from '../icons';
import { Button } from '../ui/Button';
import { cx } from '../ui/cx';

export interface StageCanvasProps {
  aspect?: '9:16' | '16:9';
  children: ReactNode;
  headerRight?: ReactNode;
  safeZoneActive?: boolean;
  onToggleSafeZone?: () => void;
  onOpenContactSheet?: () => void;
  contactSheetBusy?: boolean;
  onPlayPreview?: () => void;
  playPreviewLabel?: string;
  footerExtras?: ReactNode;
  className?: string;
}

/**
 * Sân khấu Xem trước trung tâm chuẩn VEED.IO (`--bg-canvas`: #ECEFF4 Light / #090B0F Dark).
 * Căn giữa khung video 9:16 hoặc 16:9, bên dưới chỉ đặt tối đa 3 nút công cụ gọn nhẹ.
 */
export function StageCanvas({
  aspect = '9:16',
  children,
  headerRight,
  safeZoneActive,
  onToggleSafeZone,
  onOpenContactSheet,
  contactSheetBusy,
  onPlayPreview,
  playPreviewLabel = vi.studioShell.canvasPlayBtn,
  footerExtras,
  className,
}: StageCanvasProps) {
  return (
    <section
      aria-label="Sân khấu xem trước video"
      className={cx(
        'flex flex-1 flex-col items-center justify-between gap-3 bg-[var(--bg-canvas)] p-4 lg:p-5',
        className,
      )}
    >
      <div className="flex w-full items-center justify-between gap-2">
        <span className="rounded-pill border border-line bg-card px-2.5 py-0.5 text-tiny font-semibold text-muted tabular-nums">
          Canvas · {aspect === '16:9' ? '1920 × 1080 (16:9)' : '1080 × 1920 (9:16)'}
        </span>
        {headerRight && <div className="flex items-center gap-2">{headerRight}</div>}
      </div>

      <div className="flex w-full flex-1 items-center justify-center">
        <div
          className={cx(
            'relative overflow-hidden rounded-preview border border-line bg-card shadow-card',
            aspect === '9:16'
              ? 'aspect-[9/16] w-full max-w-[310px]'
              : 'aspect-video w-full max-w-[620px]',
          )}
        >
          {children}
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-center gap-2 rounded-pill border border-line bg-card px-3 py-1.5 shadow-card">
        {onPlayPreview && (
          <Button
            tone="soft"
            size="sm"
            icon={<PlayIcon size={13} />}
            onClick={onPlayPreview}
            className="!min-h-[30px] !px-2.5 !text-tiny"
          >
            {playPreviewLabel}
          </Button>
        )}
        {onToggleSafeZone && (
          <Button
            tone={safeZoneActive ? 'ink' : 'soft'}
            size="sm"
            icon={<EyeIcon size={13} />}
            onClick={onToggleSafeZone}
            aria-pressed={safeZoneActive}
            className="!min-h-[30px] !px-2.5 !text-tiny"
          >
            {vi.studioShell.canvasSafeZoneBtn}
          </Button>
        )}
        {onOpenContactSheet && (
          <Button
            tone="soft"
            size="sm"
            icon={<GripIcon size={13} />}
            busy={contactSheetBusy}
            onClick={onOpenContactSheet}
            className="!min-h-[30px] !px-2.5 !text-tiny"
          >
            {vi.studioShell.canvasContactSheetBtn}
          </Button>
        )}
        {footerExtras}
      </div>
    </section>
  );
}
