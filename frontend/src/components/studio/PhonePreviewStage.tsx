import type { ReactNode } from 'react';
import { PlayIcon, UploadIcon } from '../icons';
import { SafeZoneOverlay, SafeZoneToolbar, type SafeZonePlatform } from '../SafeZoneOverlay';
import { WatermarkControl } from '../WatermarkControl';
import { Button } from '../ui/Button';

export interface PhonePreviewStageProps {
  title?: string;
  badgeText?: string;
  safeZone: SafeZonePlatform;
  onSafeZoneChange: (p: SafeZonePlatform) => void;
  estimateText?: string;
  onPreview?: () => void;
  onExport?: () => void;
  previewBusy?: boolean;
  exportBusy?: boolean;
  previewDisabled?: boolean;
  exportDisabled?: boolean;
  previewLabel?: string;
  exportLabel?: string;
  showWatermarkControl?: boolean;
  footer?: ReactNode;
  children: ReactNode;
}

/**
 * Khung mô phỏng màn hình điện thoại 9:16 dùng chung cho 3 động cơ:
 * Tích hợp Safe-Zone (TikTok / Shorts / Reels), Watermark HBT Studio,
 * ước tính thời gian và 2 nút phân cấp Xem nhanh (Preview) vs Xuất bản đẹp (Final).
 */
export function PhonePreviewStage({
  title = 'Xem trước 9:16',
  badgeText,
  safeZone,
  onSafeZoneChange,
  estimateText,
  onPreview,
  onExport,
  previewBusy,
  exportBusy,
  previewDisabled,
  exportDisabled,
  previewLabel = 'Xem nhanh (Preview)',
  exportLabel = 'Xuất bản đẹp (1080×1920)',
  showWatermarkControl = true,
  footer,
  children,
}: PhonePreviewStageProps) {
  return (
    <section
      aria-label={title}
      className="space-y-3.5 rounded-card border border-line bg-card p-4 shadow-card"
    >
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-tiny font-extrabold uppercase tracking-wider text-muted">{title}</h2>
        {badgeText && (
          <span className="rounded-pill bg-soft px-2.5 py-0.5 text-tiny font-bold text-text-2">
            {badgeText}
          </span>
        )}
      </div>

      <div className="flex justify-center">
        <SafeZoneToolbar platform={safeZone} onChange={onSafeZoneChange} />
      </div>

      <div className="relative mx-auto aspect-[9/16] w-full max-w-[290px] overflow-hidden rounded-[24px] border-2 border-line-input bg-hero shadow-lg">
        <SafeZoneOverlay platform={safeZone} />
        {children}
      </div>

      {showWatermarkControl && <WatermarkControl />}

      {estimateText && (
        <p className="num text-center text-tiny font-semibold text-muted">{estimateText}</p>
      )}

      {(onPreview || onExport) && (
        <div className="grid grid-cols-1 gap-2 pt-1">
          {onExport && (
            <Button
              tone="export"
              busy={exportBusy}
              disabled={exportDisabled}
              icon={<UploadIcon size={16} />}
              onClick={onExport}
              className="w-full"
            >
              {exportLabel}
            </Button>
          )}
          {onPreview && (
            <Button
              tone="soft"
              size="sm"
              busy={previewBusy}
              disabled={previewDisabled}
              icon={<PlayIcon size={14} />}
              onClick={onPreview}
              className="w-full"
            >
              {previewLabel}
            </Button>
          )}
        </div>
      )}

      {footer}
    </section>
  );
}
