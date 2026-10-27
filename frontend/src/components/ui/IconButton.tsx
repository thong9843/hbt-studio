import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react';
import { cx } from './cx';
import './ui.css';

interface Props extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'aria-label'> {
  /** Bắt buộc: nút chỉ có biểu tượng phải có tên tiếng Việt. */
  label: string;
  small?: boolean;
  children: ReactNode;
}

/** Nút tròn 36-44 px chỉ có biểu tượng. */
export const IconButton = forwardRef<HTMLButtonElement, Props>(function IconButton(
  { label, small, className, children, type = 'button', ...rest },
  ref,
) {
  return (
    <button
      {...rest}
      ref={ref}
      type={type}
      aria-label={label}
      title={rest.title ?? label}
      className={cx('ui-icon-btn', small && 'ui-icon-btn-sm', className)}
    >
      {children}
    </button>
  );
});
