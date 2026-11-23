import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from 'react';
import { cx } from './cx';
import './ui.css';

export interface StudioSelectOption {
  value: string;
  label: string;
  description?: string;
  icon?: ReactNode;
  disabled?: boolean;
}

export interface StudioSelectProps {
  options: StudioSelectOption[];
  value: string;
  onChange: (value: string) => void;
  label?: string;
  'aria-label'?: string;
  id?: string;
  placeholder?: string;
  disabled?: boolean;
  variant?: 'field' | 'pill' | 'compact';
  autoWidth?: boolean;
  className?: string;
  triggerClassName?: string;
  menuClassName?: string;
}

/**
 * Custom Dropdown chuẩn HBT Studio Pro Craft — thay thế 100% thẻ `<select>` gốc trình duyệt.
 * - Bề mặt nâng cao (`--bg-elevated`), viền 1px sắc nét, chevron xoay mượt 180°.
 * - Menu bo góc 12px mở bằng GPU `opacity + translateY(-4px) + scale(0.98)` (140ms).
 * - Đầy đủ bàn phím (ArrowUp/Down, Home/End, Enter, Space, Escape) và đóng khi click ngoài.
 */
export function StudioSelect({
  options,
  value,
  onChange,
  label,
  'aria-label': ariaLabel,
  id: idProp,
  placeholder = 'Chọn một mục…',
  disabled = false,
  variant = 'field',
  autoWidth = false,
  className,
  triggerClassName,
  menuClassName,
}: StudioSelectProps) {
  const autoId = useId();
  const id = idProp ?? autoId;
  const listboxId = `${id}-listbox`;
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  const [open, setOpen] = useState(false);
  const selectedIndex = useMemo(
    () => options.findIndex((opt) => opt.value === value),
    [options, value],
  );
  const [highlighted, setHighlighted] = useState<number>(Math.max(0, selectedIndex));

  useEffect(() => {
    if (!open) return;
    setHighlighted(selectedIndex >= 0 ? selectedIndex : 0);
  }, [open, selectedIndex]);

  useEffect(() => {
    if (!open) return;
    const onOutside = (ev: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(ev.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onOutside);
    return () => document.removeEventListener('mousedown', onOutside);
  }, [open]);

  const selectedOption = selectedIndex >= 0 ? options[selectedIndex] : null;

  const moveHighlight = (dir: 1 | -1) => {
    if (options.length === 0) return;
    let next = highlighted;
    for (let step = 0; step < options.length; step++) {
      next = (next + dir + options.length) % options.length;
      if (!options[next]?.disabled) {
        setHighlighted(next);
        return;
      }
    }
  };

  const commitIndex = (idx: number) => {
    const opt = options[idx];
    if (!opt || opt.disabled) return;
    onChange(opt.value);
    setOpen(false);
    triggerRef.current?.focus();
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (disabled) return;
    if (!open) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        setOpen(true);
      }
      return;
    }

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        moveHighlight(1);
        break;
      case 'ArrowUp':
        e.preventDefault();
        moveHighlight(-1);
        break;
      case 'Home': {
        e.preventDefault();
        const first = options.findIndex((o) => !o.disabled);
        if (first >= 0) setHighlighted(first);
        break;
      }
      case 'End': {
        e.preventDefault();
        for (let i = options.length - 1; i >= 0; i--) {
          if (!options[i]?.disabled) {
            setHighlighted(i);
            break;
          }
        }
        break;
      }
      case 'Enter':
      case ' ':
        e.preventDefault();
        commitIndex(highlighted);
        break;
      case 'Escape':
        e.preventDefault();
        setOpen(false);
        triggerRef.current?.focus();
        break;
      case 'Tab':
        setOpen(false);
        break;
      default:
        break;
    }
  };

  const control = (
    <div
      ref={rootRef}
      className={cx(
        'ui-studio-select',
        autoWidth && 'ui-studio-select-auto',
        variant === 'pill' && 'ui-studio-select-pill',
        variant === 'compact' && 'ui-studio-select-compact',
        className,
      )}
    >
      <button
        ref={triggerRef}
        id={id}
        type="button"
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listboxId}
        aria-label={ariaLabel ?? label}
        aria-activedescendant={
          open && options[highlighted] ? `${id}-opt-${highlighted}` : undefined
        }
        data-value={value}
        disabled={disabled}
        onClick={() => !disabled && setOpen((v) => !v)}
        onKeyDown={handleKeyDown}
        className={cx('ui-studio-select-trigger', triggerClassName)}
      >
        <span className="ui-studio-select-value">
          {selectedOption?.icon}
          <span className="truncate">{selectedOption ? selectedOption.label : placeholder}</span>
        </span>
        <svg
          className="ui-studio-select-caret"
          width={variant === 'compact' ? 14 : 15}
          height={variant === 'compact' ? 14 : 15}
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
      </button>

      {open && (
        <ul
          id={listboxId}
          role="listbox"
          aria-label={ariaLabel ?? label}
          className={cx('ui-studio-select-menu', menuClassName)}
        >
          {options.map((opt, idx) => {
            const isSel = opt.value === value;
            const isHi = idx === highlighted;
            return (
              <li
                key={`${opt.value}-${idx}`}
                id={`${id}-opt-${idx}`}
                role="option"
                aria-selected={isSel}
                aria-disabled={opt.disabled || undefined}
                data-highlighted={isHi ? 'true' : undefined}
                onMouseEnter={() => !opt.disabled && setHighlighted(idx)}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => commitIndex(idx)}
                className="ui-studio-select-opt"
              >
                <span className="flex min-w-0 flex-1 items-start gap-2">
                  {opt.icon && <span className="mt-0.5 shrink-0">{opt.icon}</span>}
                  <span className="min-w-0 flex-1">
                    <span className="block truncate">{opt.label}</span>
                    {opt.description && (
                      <span className="ui-studio-select-opt-desc">{opt.description}</span>
                    )}
                  </span>
                </span>
                {isSel && (
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.6"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                    className="shrink-0 text-focus"
                  >
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );

  if (!label) return control;

  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-tiny font-bold text-muted">
        {label}
      </label>
      {control}
    </div>
  );
}
