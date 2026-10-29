import { useEffect, useId, useState } from 'react';
import { formatCount, parseCount } from '../../utils/count';

interface Props {
  label: string;
  value: number | null;
  onChange: (value: number | null) => void;
  required?: boolean;
  /** Nhãn đọc cho trình đọc màn hình khi nhãn hiển thị ngắn. */
  ariaLabel?: string;
  compact?: boolean;
}

/** Ô số liệu: gõ `27,6K`, `1.8K`, `351`…; rời ô thì chuẩn hoá lại. Chỉ để hiển thị trên thẻ. */
export function StatInput({ label, value, onChange, required, ariaLabel, compact }: Props) {
  const id = useId();
  const [text, setText] = useState(formatCount(value));
  const [focused, setFocused] = useState(false);
  const invalid = text.trim() !== '' && parseCount(text) === null;

  useEffect(() => {
    if (!focused) setText(formatCount(value));
  }, [value, focused]);

  return (
    <div className="flex min-w-0 flex-col gap-1">
      {!compact && (
        <label htmlFor={id} className="ui-label">
          {label}
          {required && (
            <span className="text-brand" aria-hidden="true">
              {' '}
              *
            </span>
          )}
        </label>
      )}
      <input
        id={id}
        className="ui-input num text-right"
        style={{ height: compact ? 36 : 40 }}
        inputMode="text"
        autoComplete="off"
        aria-label={compact ? (ariaLabel ?? label) : undefined}
        aria-required={required || undefined}
        aria-invalid={invalid || undefined}
        value={text}
        onFocus={() => setFocused(true)}
        onChange={(e) => {
          setText(e.target.value);
          const n = parseCount(e.target.value);
          if (n !== null) onChange(n);
          else if (e.target.value.trim() === '') onChange(null);
        }}
        onBlur={() => {
          setFocused(false);
          setText(formatCount(parseCount(text) ?? (text.trim() === '' ? null : value)));
        }}
      />
    </div>
  );
}
