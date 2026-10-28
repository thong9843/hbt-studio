import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { cx } from './cx';
import { IconButton } from './IconButton';
import './ui.css';

export interface MenuItem {
  key: string;
  label: string;
  onSelect: () => void;
  danger?: boolean;
  disabled?: boolean;
  /** Lý do khoá (vd "Đang dựng"), hiện ở `title`. */
  reason?: string;
}

interface Props {
  /** Tên nút mở menu (tiếng Việt, đọc cho trình đọc màn hình). */
  label: string;
  icon: ReactNode;
  items: MenuItem[];
  align?: 'start' | 'end';
}

/** Nút ⋯ mở danh sách việc. Mũi tên lên/xuống và Tab đổi dòng (focus không ra khỏi menu), Esc đóng và trả focus về nút. */
export function Menu({ label, icon, items, align = 'end' }: Props) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    root.current?.querySelector<HTMLElement>('[role=menuitem]:not([disabled])')?.focus();
    const onDown = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [open]);

  const close = () => {
    setOpen(false);
    button.current?.focus();
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (!open) return;
    if (e.key === 'Escape') {
      e.stopPropagation();
      close();
    } else if (e.key === 'Tab' || e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      // Tab xoay vòng trong menu như mũi tên (focus không ra ngoài khi menu còn mở).
      e.preventDefault();
      const list = Array.from(
        root.current?.querySelectorAll<HTMLElement>('[role=menuitem]:not([disabled])') ?? [],
      );
      if (list.length === 0) return;
      const at = list.indexOf(document.activeElement as HTMLElement);
      const step = e.key === 'ArrowUp' || (e.key === 'Tab' && e.shiftKey) ? -1 : 1;
      list[(at + step + list.length) % list.length].focus();
    } else if (e.key === 'Home' || e.key === 'End') {
      e.preventDefault();
      const list = root.current?.querySelectorAll<HTMLElement>('[role=menuitem]:not([disabled])');
      if (list?.length) list[e.key === 'Home' ? 0 : list.length - 1].focus();
    }
  };

  return (
    <div ref={root} className="relative inline-block" onKeyDown={onKeyDown}>
      <IconButton
        ref={button}
        label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        onClick={() => setOpen((v) => !v)}
      >
        {icon}
      </IconButton>
      {open && (
        <div
          id={id}
          role="menu"
          aria-label={label}
          className={cx('ui-menu top-full mt-1', align === 'end' ? 'right-0' : 'left-0')}
        >
          {items.map((it) => (
            <button
              key={it.key}
              type="button"
              role="menuitem"
              disabled={it.disabled}
              title={it.disabled ? it.reason : undefined}
              className={cx('ui-row', it.danger && 'ui-row-danger')}
              onClick={() => {
                close();
                it.onSelect();
              }}
            >
              {it.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
