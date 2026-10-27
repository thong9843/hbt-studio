import type { ButtonHTMLAttributes } from 'react';
import { cx } from './cx';
import './ui.css';

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Đang chọn (nền mực). Chip là nút bật/tắt hoặc một lựa chọn trong nhóm. */
  selected?: boolean;
  small?: boolean;
}

export function Chip({ selected, small, className, type = 'button', ...rest }: Props) {
  return (
    <button
      {...rest}
      type={type}
      aria-pressed={selected}
      className={cx('ui-chip', small && 'ui-chip-sm', className)}
    />
  );
}
