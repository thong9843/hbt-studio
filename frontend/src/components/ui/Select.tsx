import { useId, type SelectHTMLAttributes } from 'react';
import { cx } from './cx';
import './ui.css';

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
  /** Kiểu dáng: 'field' (chuẩn 44px), 'pill' (bo tròn như chip), 'compact' (nhỏ gọn trong thẻ). */
  variant?: 'field' | 'pill' | 'compact';
  /** Co theo nội dung thay vì full-width. */
  autoWidth?: boolean;
  wrapClassName?: string;
}

/** Dropdown thống nhất toàn dự án (bọc native select giữ 100% accessibility + bàn phím). */
export function Select({
  label,
  error,
  variant = 'field',
  autoWidth = false,
  className,
  wrapClassName,
  id: idProp,
  children,
  ...rest
}: SelectProps) {
  const auto = useId();
  const id = idProp ?? auto;

  const selectEl = (
    <div
      className={cx(
        'ui-select-wrap',
        autoWidth && 'ui-select-wrap-auto',
        variant === 'compact' && 'ui-select-wrap-compact',
        wrapClassName,
      )}
    >
      <select
        {...rest}
        id={id}
        aria-invalid={error ? true : undefined}
        className={cx(
          'ui-select',
          variant === 'pill' && 'ui-select-pill',
          variant === 'compact' && 'ui-select-compact',
          className,
        )}
      >
        {children}
      </select>
      <svg
        className="ui-select-caret"
        width={variant === 'compact' ? 14 : 16}
        height={variant === 'compact' ? 14 : 16}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <polyline points="6 9 12 15 18 9" />
      </svg>
    </div>
  );

  if (!label && !error) return selectEl;

  return (
    <div className="ui-field">
      {label && (
        <label htmlFor={id} className="ui-label">
          {label}
        </label>
      )}
      {selectEl}
      {error && (
        <p className="ui-field-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
