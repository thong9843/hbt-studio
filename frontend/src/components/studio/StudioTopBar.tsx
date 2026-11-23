import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { vi } from '../../i18n/vi';
import { ArrowLeftIcon, MoreIcon } from '../icons';
import { Menu, type MenuItem } from '../ui/Menu';
import { SegmentedControl } from '../ui/SegmentedControl';
import { ExportPopover, type ExportPopoverProps } from './ExportPopover';

export interface StudioTopBarProps {
  engineBadge?: string;
  title?: string;
  savedText?: string;
  projectSelector?: ReactNode;
  projectMenuItems?: MenuItem[];
  aspect?: '9:16' | '16:9';
  onAspectChange?: (next: '9:16' | '16:9') => void;
  aspectAriaLabel?: string;
  exportProps?: ExportPopoverProps;
  rightExtras?: ReactNode;
}

/**
 * Thanh Topbar 56px tối giản tuyệt đối chuẩn VEED.IO — CHỈ giữ đúng 4 cụm điều khiển:
 * 1. Trái: Nút [←] · Dropdown chọn dự án (kèm tên dự án đang mở) · Menu ⋯ (Đổi tên, Xóa dự án) · Nhãn Đã lưu.
 * 2. Phải: Bộ chọn tỷ lệ [9:16 | 16:9] · DUY NHẤT 1 nút đỏ Xuất video (Popover).
 */
export function StudioTopBar({
  engineBadge,
  title,
  savedText = vi.studioShell.savedBadge,
  projectSelector,
  projectMenuItems,
  aspect,
  onAspectChange,
  aspectAriaLabel = 'Tỉ lệ khung hình',
  exportProps,
  rightExtras,
}: StudioTopBarProps) {
  return (
    <header className="flex h-[56px] shrink-0 items-center justify-between gap-3 border-b border-line bg-card px-3.5">
      <div className="flex min-w-0 flex-1 items-center gap-2">
        <Link
          to="/"
          aria-label={vi.studioShell.backToHome}
          title={vi.studioShell.backToHome}
          className="ui-icon-btn ui-icon-btn-sm shrink-0 border border-line bg-soft text-text"
        >
          <ArrowLeftIcon size={15} />
        </Link>

        {projectSelector ? (
          <div className="flex min-w-0 max-w-[260px] items-center gap-1.5 lg:max-w-[360px]">
            {projectSelector}
          </div>
        ) : (
          <div className="flex min-w-0 max-w-[260px] items-center gap-2 lg:max-w-[360px]">
            {engineBadge && (
              <span className="shrink-0 whitespace-nowrap rounded-pill bg-[var(--accent-soft)] px-2.5 py-1 text-[13px] font-semibold text-[var(--on-accent-soft)]">
                {engineBadge}
              </span>
            )}
            {title && (
              <h1 className="truncate text-small font-bold tracking-tight text-text">{title}</h1>
            )}
          </div>
        )}

        {projectMenuItems && projectMenuItems.length > 0 && (
          <Menu
            label={vi.studioShell.projectActionsMenu}
            icon={<MoreIcon size={16} />}
            items={projectMenuItems}
            align="start"
          />
        )}

        {savedText && (
          <span className="inline-flex shrink-0 items-center gap-1.5 rounded-pill bg-soft px-2 py-0.5 text-[11px] font-semibold text-muted">
            <span className="h-1.5 w-1.5 rounded-full bg-ok" aria-hidden="true" />
            {savedText}
          </span>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-2">
        {aspect && onAspectChange && (
          <SegmentedControl
            roleMode="button"
            aria-label={aspectAriaLabel}
            value={aspect}
            onChange={onAspectChange}
            options={[
              { value: '9:16', label: '9:16' },
              { value: '16:9', label: '16:9' },
            ]}
          />
        )}

        {rightExtras}

        {exportProps && <ExportPopover {...exportProps} />}
      </div>
    </header>
  );
}
