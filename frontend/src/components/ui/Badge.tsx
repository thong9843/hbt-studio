import type { HTMLAttributes } from 'react';
import { cx } from './cx';
import './ui.css';

export type BadgeTone = 'neutral' | 'red' | 'yel' | 'ok' | 'danger';

interface Props extends HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone;
}

/** Nhãn trạng thái. Luôn có chữ; màu chỉ là phụ (DESIGN-HBT mục 8). */
export function Badge({ tone = 'neutral', className, ...rest }: Props) {
  return (
    <span
      {...rest}
      className={cx('ui-badge', tone !== 'neutral' && `ui-badge-${tone}`, className)}
    />
  );
}
