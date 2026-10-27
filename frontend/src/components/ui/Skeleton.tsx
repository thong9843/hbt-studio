import type { CSSProperties } from 'react';
import { vi } from '../../i18n/vi';
import { cx } from './cx';
import './ui.css';

interface Props {
  width?: CSSProperties['width'];
  height?: CSSProperties['height'];
  className?: string;
}

/** Khung xương đang tải: tĩnh, màu `--soft`, không hiệu ứng lấp lánh. */
export function Skeleton({ width = '100%', height = 16, className }: Props) {
  return (
    <div
      role="status"
      aria-label={vi.ui.loading}
      className={cx('ui-skeleton', className)}
      style={{ width, height }}
    />
  );
}
