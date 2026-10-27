import { vi } from '../i18n/vi';
import { Button } from './ui/Button';
import { Dialog } from './ui/Dialog';

interface Props {
  title: string;
  message: string;
  confirmLabel: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Hộp thoại xác nhận (xoá…). Esc đóng; focus vào "Huỷ"; nút chính nằm bên phải. */
export function ConfirmDialog({
  title,
  message,
  confirmLabel,
  danger,
  busy,
  onConfirm,
  onCancel,
}: Props) {
  return (
    <Dialog
      open
      role="alertdialog"
      title={title}
      onClose={onCancel}
      footer={
        <>
          <Button tone="soft" data-autofocus onClick={onCancel}>
            {vi.common.cancel}
          </Button>
          <Button tone={danger ? 'danger' : 'ink'} disabled={busy} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <p className="text-muted">{message}</p>
    </Dialog>
  );
}
