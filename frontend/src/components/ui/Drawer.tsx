import { useId, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { vi } from '../../i18n/vi';
import { XIcon } from '../icons';
import { IconButton } from './IconButton';
import { useModal, usePresence } from './overlay';
import './ui.css';

interface Props {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}

/** Ngăn kéo bên phải (xem trước dưới 1024 px). Cùng luật focus/Esc như hộp thoại. */
export function Drawer({ open, onClose, title, children }: Props) {
  const { mounted, closing } = usePresence(open);
  const ref = useRef<HTMLDivElement>(null);
  const id = useId();
  useModal(ref, open && mounted, onClose);
  if (!mounted) return null;
  return createPortal(
    <div
      className="ui-scrim ui-scrim-end"
      data-closing={closing}
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${id}-t`}
        tabIndex={-1}
        className="ui-drawer"
      >
        <div className="mb-4 flex items-center justify-between gap-4">
          <h2 id={`${id}-t`} className="text-title font-extrabold">
            {title}
          </h2>
          <IconButton label={vi.common.close} small onClick={onClose}>
            <XIcon size={18} />
          </IconButton>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  );
}
