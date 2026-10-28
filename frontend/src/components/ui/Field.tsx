import {
  useId,
  type InputHTMLAttributes,
  type ReactNode,
  type TextareaHTMLAttributes,
} from 'react';
import { cx } from './cx';
import './ui.css';

interface Common {
  label?: string;
  /** Lỗi: viền `--danger`, chữ lỗi dưới ô. */
  error?: string;
  /** Giới hạn: hiện bộ đếm `n/giới hạn`; vượt thì viền `--accent`, bộ đếm nền vàng. */
  limit?: number;
  /** Số đếm hiển thị thay cho độ dài của ô (vd tổng lời đọc cả video). Chỉ có nghĩa khi có `limit`. */
  count?: number;
  /** Chú thích (tooltip) của bộ đếm. */
  countTitle?: string;
  hint?: ReactNode;
}

type InputProps = Common & InputHTMLAttributes<HTMLInputElement>;
type AreaProps = Common & TextareaHTMLAttributes<HTMLTextAreaElement>;

/** Đếm theo ký tự Unicode sau NFC, khớp backend (13.B4.2). */
function length(value: unknown): number {
  return typeof value === 'string' ? [...value.normalize('NFC')].length : 0;
}

function Counter({
  id,
  limit,
  value,
  count,
  title,
}: {
  id: string;
  limit?: number;
  value: unknown;
  count?: number;
  title?: string;
}) {
  if (limit === undefined) return null;
  const n = count ?? length(value);
  return (
    <span
      id={`${id}-count`}
      data-over={n > limit}
      className="ui-counter"
      aria-live="polite"
      title={title}
    >
      {n}/{limit}
    </span>
  );
}

function FieldError({ id, error }: { id: string; error?: string }) {
  if (!error) return null;
  return (
    <p id={`${id}-err`} className="ui-field-error" role="alert">
      {error}
    </p>
  );
}

function aria(id: string, error?: string, limit?: number) {
  const ids = [error && `${id}-err`, limit !== undefined && `${id}-count`].filter(Boolean);
  return {
    'aria-invalid': error ? true : undefined,
    'aria-describedby': ids.length ? ids.join(' ') : undefined,
  };
}

/** Ô nhập một dòng, cao 48, bo 14. */
export function Input({
  label,
  error,
  limit,
  count,
  countTitle,
  hint,
  className,
  id: idProp,
  ...rest
}: InputProps) {
  const auto = useId();
  const id = idProp ?? auto;
  const over = limit !== undefined && (count ?? length(rest.value)) > limit;
  return (
    <div className="ui-field">
      {label && (
        <label htmlFor={id} className="ui-label">
          {label}
        </label>
      )}
      <div className="ui-control" data-kind="input">
        <input
          {...rest}
          id={id}
          data-over={over || undefined}
          data-counter={limit !== undefined || undefined}
          {...aria(id, error, limit)}
          className={cx('ui-input', className)}
        />
        <Counter id={id} limit={limit} value={rest.value} count={count} title={countTitle} />
      </div>
      {hint}
      <FieldError id={id} error={error} />
    </div>
  );
}

/** Ô nhiều dòng (lời đọc). */
export function Textarea({
  label,
  error,
  limit,
  count,
  countTitle,
  hint,
  className,
  id: idProp,
  ...rest
}: AreaProps) {
  const auto = useId();
  const id = idProp ?? auto;
  const over = limit !== undefined && (count ?? length(rest.value)) > limit;
  return (
    <div className="ui-field">
      {label && (
        <label htmlFor={id} className="ui-label">
          {label}
        </label>
      )}
      <div className="ui-control" data-kind="textarea">
        <textarea
          {...rest}
          id={id}
          data-over={over || undefined}
          data-counter={limit !== undefined || undefined}
          {...aria(id, error, limit)}
          className={cx('ui-input', className)}
        />
        <Counter id={id} limit={limit} value={rest.value} count={count} title={countTitle} />
      </div>
      {hint}
      <FieldError id={id} error={error} />
    </div>
  );
}
