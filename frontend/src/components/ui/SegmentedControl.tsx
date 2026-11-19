import type { ReactNode } from 'react';
import { cx } from './cx';
import './ui.css';

export interface SegmentedOption<T extends string = string> {
  value: T;
  label: string;
  icon?: ReactNode;
  disabled?: boolean;
}

export interface SegmentedControlProps<T extends string = string> {
  options: readonly SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
  'aria-label': string;
  /** 'radio' cho nhóm chọn giá trị, 'tab' cho thanh chuyển tab, 'button' cho nhóm nút bấm. */
  roleMode?: 'radio' | 'tab' | 'button';
  fullWidth?: boolean;
  className?: string;
}

/**
 * Thanh chọn dạng viên thuốc với active thumb trượt mượt bằng GPU `transform: translateX()` (160ms).
 */
export function SegmentedControl<T extends string = string>({
  options,
  value,
  onChange,
  'aria-label': ariaLabel,
  roleMode = 'radio',
  fullWidth = false,
  className,
}: SegmentedControlProps<T>) {
  const count = Math.max(1, options.length);
  const activeIdx = Math.max(
    0,
    options.findIndex((o) => o.value === value),
  );

  return (
    <div
      role={roleMode === 'tab' ? 'tablist' : roleMode === 'button' ? 'group' : 'radiogroup'}
      aria-label={ariaLabel}
      className={cx('ui-segmented', fullWidth && 'ui-segmented-full', className)}
    >
      <span
        aria-hidden="true"
        className="ui-segmented-thumb"
        style={{
          width: `calc((100% - 6px) / ${count})`,
          transform: `translateX(${activeIdx * 100}%)`,
        }}
      />
      {options.map((opt) => {
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            type="button"
            role={roleMode === 'tab' ? 'tab' : roleMode === 'button' ? undefined : 'radio'}
            aria-selected={roleMode === 'tab' ? active : undefined}
            aria-checked={roleMode === 'radio' ? active : undefined}
            aria-pressed={roleMode === 'button' ? active : undefined}
            data-active={active ? 'true' : 'false'}
            disabled={opt.disabled}
            onClick={() => !opt.disabled && onChange(opt.value)}
            className="ui-segmented-btn"
          >
            {opt.icon}
            <span>{opt.label}</span>
          </button>
        );
      })}
    </div>
  );
}
