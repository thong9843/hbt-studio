import { useEffect, useRef, type ReactNode } from 'react';
import { cx } from './cx';

export interface PopoverProps {
  open: boolean;
  onClose: () => void;
  trigger: ReactNode;
  children: ReactNode;
  align?: 'left' | 'right';
  ariaLabel?: string;
  className?: string;
  panelClassName?: string;
}

/**
 * Khung Popover nổi chuẩn VEED.IO (14px radius, đóng khi click ra ngoài hoặc nhấn Escape).
 * Không dùng backdrop-blur diện rộng để đảm bảo 0% lag trên máy CPU i5-10400.
 */
export function Popover({
  open,
  onClose,
  trigger,
  children,
  align = 'right',
  ariaLabel,
  className,
  panelClassName,
}: PopoverProps) {
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open, onClose]);

  return (
    <div ref={rootRef} className={cx('relative inline-flex items-center', className)}>
      {trigger}
      {open && (
        <div
          role="dialog"
          aria-label={ariaLabel}
          className={cx(
            'absolute top-[calc(100%+8px)] z-50 w-[340px] max-w-[calc(100vw-24px)] rounded-card border border-line bg-card p-4 shadow-pop',
            align === 'right' ? 'right-0' : 'left-0',
            panelClassName,
          )}
        >
          {children}
        </div>
      )}
    </div>
  );
}
