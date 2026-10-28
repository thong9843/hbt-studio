import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { vi } from '../../i18n/vi';
import { cx } from './cx';
import './ui.css';

export type ButtonTone = 'ink' | 'accent' | 'brand' | 'soft' | 'danger' | 'ghost';

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  tone?: ButtonTone;
  size?: 'sm' | 'md' | 'lg';
  /** Đang chạy việc: hiện vòng xoay, nút không bấm được. */
  busy?: boolean;
  /** Lý do tắt, hiện ở `title` và đọc cho trình đọc màn hình (vd "Thiếu ảnh cảnh 3"). */
  reason?: string;
  icon?: ReactNode;
}

/**
 * Nút viên thuốc cao 48 (54 ở cột xem trước). Ba màu chính: mực, vàng, đỏ.
 * Luôn render `<button>`. Liên kết (điều hướng, tải file) viết `<a className="ui-btn ui-btn-soft">`
 * hoặc `<Link className="ui-btn ...">`, không truyền `href` / `to` / `as` vào đây.
 */
export function Button({
  tone = 'ink',
  size = 'md',
  busy,
  reason,
  icon,
  disabled,
  className,
  children,
  title,
  type = 'button',
  ...rest
}: Props) {
  const off = Boolean(disabled || busy);
  return (
    <button
      {...rest}
      type={type}
      disabled={off}
      aria-busy={busy || undefined}
      title={off && reason ? reason : title}
      className={cx(
        'ui-btn',
        `ui-btn-${tone}`,
        size === 'lg' && 'ui-btn-lg',
        size === 'sm' && 'ui-btn-sm',
        className,
      )}
    >
      {busy ? (
        <>
          <span className="ui-spinner" aria-hidden="true" />
          <span className="sr-only">{vi.ui.busy}</span>
        </>
      ) : (
        icon
      )}
      {children}
      {off && reason && <span className="sr-only"> ({reason})</span>}
    </button>
  );
}
