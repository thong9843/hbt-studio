import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { vi } from '../../i18n/vi';
import { ArrowLeftIcon, DownloadIcon, PlayIcon } from '../icons';
import { Button } from '../ui/Button';
import { SegmentedControl } from '../ui/SegmentedControl';
import { ExportPopover, type ExportPopoverProps } from './ExportPopover';

export interface StudioTopBarProps {
  engineBadge: string;
  title: string;
  savedText?: string;
  projectSelector?: ReactNode;
  aspect?: '9:16' | '16:9';
  onAspectChange?: (next: '9:16' | '16:9') => void;
  aspectAriaLabel?: string;
  onQuickPreview?: () => void;
  quickPreviewLabel?: string;
  quickPreviewDisabled?: boolean;
  quickPreviewBusy?: boolean;
  inlineFinalLabel?: string;
  onInlineFinal?: () => void;
  inlineFinalDisabled?: boolean;
  inlineFinalBusy?: boolean;
  exportProps?: ExportPopoverProps;
  rightExtras?: ReactNode;
}

/**
 * Thanh Topbar 56px chuẩn VEED.IO:
 * Góc trái: Nút quay lại + Huy hiệu động cơ + Tên dự án / Bộ chọn dự án + Nhãn Đã lưu.
 * Góc phải: Chọn khổ 9:16 | 16:9 + Xem nhanh + Nút Xuất bản đẹp & Popover Cấu hình Xuất.
 */
export function StudioTopBar({
  engineBadge,
  title,
  savedText = vi.studioShell.savedBadge,
  projectSelector,
  aspect,
  onAspectChange,
  aspectAriaLabel = 'Tỉ lệ khung hình',
  onQuickPreview,
  quickPreviewLabel = vi.studioShell.previewQuickBtn,
  quickPreviewDisabled = false,
  quickPreviewBusy = false,
  inlineFinalLabel,
  onInlineFinal,
  inlineFinalDisabled = false,
  inlineFinalBusy = false,
  exportProps,
  rightExtras,
}: StudioTopBarProps) {
  return (
    <header className="flex min-h-[56px] flex-wrap items-center justify-between gap-3 border-b border-line bg-card px-4 py-2">
      <div className="flex min-w-0 flex-wrap items-center gap-2.5">
        <Link
          to="/"
          aria-label={vi.studioShell.backToHome}
          title={vi.studioShell.backToHome}
          className="ui-icon-btn ui-icon-btn-sm border border-line bg-soft text-text"
        >
          <ArrowLeftIcon size={15} />
        </Link>
        <span className="rounded-pill bg-[var(--accent-soft)] px-2.5 py-0.5 text-tiny font-bold text-[var(--on-accent-soft)]">
          {engineBadge}
        </span>
        <h1 className="truncate text-body font-bold tracking-tight text-text">{title}</h1>
        {savedText && (
          <span className="rounded-pill bg-soft px-2 py-0.5 text-[11px] font-semibold text-muted">
            {savedText}
          </span>
        )}
        {projectSelector && <div className="flex items-center gap-2">{projectSelector}</div>}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {aspect && onAspectChange && (
          <SegmentedControl
            aria-label={aspectAriaLabel}
            value={aspect}
            onChange={onAspectChange}
            options={[
              { value: '9:16', label: '9:16 Shorts' },
              { value: '16:9', label: '16:9 Ngang' },
            ]}
          />
        )}

        {onQuickPreview && (
          <Button
            tone="soft"
            size="sm"
            icon={<PlayIcon size={14} />}
            disabled={quickPreviewDisabled}
            busy={quickPreviewBusy}
            onClick={onQuickPreview}
          >
            {quickPreviewLabel}
          </Button>
        )}

        {onInlineFinal && inlineFinalLabel && (
          <Button
            tone="brand"
            size="sm"
            icon={<DownloadIcon size={14} />}
            disabled={inlineFinalDisabled}
            busy={inlineFinalBusy}
            onClick={onInlineFinal}
          >
            {inlineFinalLabel}
          </Button>
        )}

        {rightExtras}

        {exportProps && <ExportPopover {...exportProps} />}
      </div>
    </header>
  );
}
