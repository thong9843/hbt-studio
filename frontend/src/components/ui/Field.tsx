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
  hint?: ReactNode;
}

type InputProps = Common & InputHTMLAttributes<HTMLInputElement>;
type AreaProps = Common & TextareaHTMLAttributes<HTMLTextAreaElement>;

/** Đếm theo ký tự Unicode sau NFC, khớp backend (13.B4.2). */
function length(value: unknown): number {
  return typeof value === 'string' ? [...value.normalize('NFC')].length : 0;
}

function Meta({
  id,
  error,
  limit,
  value,
}: {
  id: string;
  error?: string;
  limit?: number;
  value: unknown;
}) {
  const n = length(value);
  const over = limit !== undefined && n > limit;
  return (
    <>
      {error && (
        <p id={`${id}-err`} className="ui-field-error" role="alert">
          {error}
        </p>
      )}
      {limit !== undefined && (
        <p id={`${id}-count`} className="mt-1 text-right">
          <span data-over={over} className="ui-counter" aria-live="polite">
            {n}/{limit}
          </span>
        </p>
      )}
    </>
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
export function Input({ label, error, limit, hint, className, id: idProp, ...rest }: InputProps) {
  const auto = useId();
  const id = idProp ?? auto;
  const over = limit !== undefined && length(rest.value) > limit;
  return (
    <div className="ui-field">
      {label && (
        <label htmlFor={id} className="ui-label">
          {label}
        </label>
      )}
      <input
        {...rest}
        id={id}
        data-over={over || undefined}
        {...aria(id, error, limit)}
        className={cx('ui-input', className)}
      />
      {hint}
      <Meta id={id} error={error} limit={limit} value={rest.value} />
    </div>
  );
}

/** Ô nhiều dòng (lời đọc). */
export function Textarea({ label, error, limit, hint, className, id: idProp, ...rest }: AreaProps) {
  const auto = useId();
  const id = idProp ?? auto;
  const over = limit !== undefined && length(rest.value) > limit;
  return (
    <div className="ui-field">
      {label && (
        <label htmlFor={id} className="ui-label">
          {label}
        </label>
      )}
      <textarea
        {...rest}
        id={id}
        data-over={over || undefined}
        {...aria(id, error, limit)}
        className={cx('ui-input', className)}
      />
      {hint}
      <Meta id={id} error={error} limit={limit} value={rest.value} />
    </div>
  );
}
