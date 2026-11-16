import type { ReactNode } from 'react';
import { PlayIcon, UploadIcon } from '../icons';
import { SafeZoneOverlay, SafeZoneToolbar, type SafeZonePlatform } from '../SafeZoneOverlay';
import { useWatermarkSettings, WatermarkControl } from '../WatermarkControl';
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
 * Tích hợp Safe-Zone (TikTok / Shorts / Reels), lớp phủ xem trước Watermark trực quan,
 * nền Xanh Chàm Hoàng Gia dịu mắt và 2 nút phân cấp Xem nhanh vs Xuất bản đẹp.
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
  const { wm } = useWatermarkSettings();
  const logoSrc = wm.logo_path
    ? wm.logo_path.startsWith('/')
      ? wm.logo_path
      : `/${wm.logo_path}`
    : '/brand/hbt-logo-mark.png';

  const wmPosClass =
    wm.position === 'bottom-left'
      ? 'bottom-[13.5%] left-3'
      : wm.position === 'top-left'
        ? 'top-[13%] left-3'
        : wm.position === 'top-right'
          ? 'top-[13%] right-3'
          : wm.position === 'center-subtle'
            ? 'inset-0 flex items-center justify-center'
            : 'bottom-[13.5%] right-3';

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

      <div
        className="relative mx-auto aspect-[9/16] w-full max-w-[300px] overflow-hidden rounded-[24px]"
        style={{
          background: 'linear-gradient(160deg, #1E1B4B 0%, #312E81 55%, #1E293B 100%)',
          border: '2px solid rgba(129, 140, 248, 0.35)',
          boxShadow: '0 16px 36px -8px rgba(49, 46, 129, 0.28)',
        }}
      >
        <SafeZoneOverlay platform={safeZone} />
        {children}

        {/* Lớp phủ xem trước Watermark trong suốt, chỉ có bóng đổ nhẹ */}
        {wm.enabled && (
          <div
            aria-hidden="true"
            style={{ opacity: wm.opacity }}
            className={`pointer-events-none absolute z-20 ${wmPosClass}`}
          >
            <div className="inline-flex items-center gap-1.5 drop-shadow-[0_2px_6px_rgba(0,0,0,0.65)]">
              {(wm.mode === 'logo' || wm.mode === 'both') && (
                <img src={logoSrc} alt="" className="h-5 w-auto object-contain" />
              )}
              {(wm.mode === 'text' || wm.mode === 'both') && (
                <span className="text-[11px] font-extrabold tracking-tight text-white">
                  {wm.text || '@HayBietTuot'}
                </span>
              )}
            </div>
          </div>
        )}
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
              size="lg"
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
