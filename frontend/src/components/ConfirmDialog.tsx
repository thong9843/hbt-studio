import { useEffect, useId, useRef } from 'react';
import { vi } from '../i18n/vi';

interface Props {
  title: string;
  message: string;
  confirmLabel: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Hộp thoại xác nhận (xoá…). Esc đóng; nút chính nằm bên phải (DESIGN-HBT.md mục 6). */
export function ConfirmDialog({
  title,
  message,
  confirmLabel,
  danger,
  busy,
  onConfirm,
  onCancel,
}: Props) {
  const id = useId();
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    cancelRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onCancel();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onCancel]);

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/50 p-4">
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={`${id}-t`}
        aria-describedby={`${id}-m`}
        className="w-full max-w-md space-y-4 rounded-frame bg-bg p-8 shadow-xl"
      >
        <h2 id={`${id}-t`}>{title}</h2>
        <p id={`${id}-m`} className="text-text-muted">
          {message}
        </p>
        <div className="flex justify-end gap-2">
          <button ref={cancelRef} type="button" className="btn btn-secondary" onClick={onCancel}>
            {vi.common.cancel}
          </button>
          <button
            type="button"
            className={`btn ${danger ? 'btn-danger' : 'btn-primary'}`}
            disabled={busy}
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
