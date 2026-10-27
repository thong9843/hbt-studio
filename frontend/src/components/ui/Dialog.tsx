import { useId, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { vi } from '../../i18n/vi';
import { XIcon } from '../icons';
import { cx } from './cx';
import { IconButton } from './IconButton';
import { useModal, usePresence } from './overlay';
import './ui.css';

interface Props {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  /** Hàng nút ở cuối (nút chính nằm bên phải). */
  footer?: ReactNode;
  /** `alertdialog` cho hộp xác nhận. */
  role?: 'dialog' | 'alertdialog';
  className?: string;
}

/**
 * Hộp thoại bo 28. Hiện: nền mờ `opacity` 150 ms + `scale(.98→1)` 180 ms; đóng 120 ms.
 * Focus vào ô đầu (hoặc phần tử có `data-autofocus`), Esc đóng, Tab không ra ngoài hộp.
 */
export function Dialog({
  open,
  onClose,
  title,
  children,
  footer,
  role = 'dialog',
  className,
}: Props) {
  const { mounted, closing } = usePresence(open);
  const ref = useRef<HTMLDivElement>(null);
  const id = useId();
  useModal(ref, open && mounted, onClose);
  if (!mounted) return null;
  return createPortal(
    <div
      className="ui-scrim"
      data-closing={closing}
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        ref={ref}
        role={role}
        aria-modal="true"
        aria-labelledby={`${id}-t`}
        tabIndex={-1}
        className={cx('ui-dialog', className)}
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <h2 id={`${id}-t`} className="text-title font-extrabold">
            {title}
          </h2>
          <IconButton label={vi.common.close} small onClick={onClose}>
            <XIcon size={18} />
          </IconButton>
        </div>
        <div>{children}</div>
        {footer && <div className="mt-6 flex justify-end gap-2">{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}
