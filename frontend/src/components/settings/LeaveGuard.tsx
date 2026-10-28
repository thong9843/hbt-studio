import { useEffect } from 'react';
import { useBlocker } from 'react-router-dom';
import { vi } from '../../i18n/vi';
import { ConfirmDialog } from '../ConfirmDialog';

/**
 * Cảnh báo khi rời màn lúc còn thay đổi chưa lưu. Chỉ gắn khi `dirty`:
 * - đổi màn trong app → hộp xác nhận (cần router dạng data router, xem `main.tsx`);
 * - đóng / tải lại tab → hộp thoại của trình duyệt (`beforeunload`).
 * Hết `dirty` (đã Lưu) hoặc rời màn thì tự gỡ.
 */
export function LeaveGuard({ dirty }: { dirty: boolean }) {
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      dirty && currentLocation.pathname !== nextLocation.pathname,
  );

  useEffect(() => {
    if (!dirty) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [dirty]);

  // Đã Lưu trong lúc hộp đang mở: không còn lý do chặn nữa.
  useEffect(() => {
    if (!dirty && blocker.state === 'blocked') blocker.proceed();
  }, [dirty, blocker]);

  if (blocker.state !== 'blocked' || !dirty) return null;
  const L = vi.settings.leave;
  return (
    <ConfirmDialog
      title={L.title}
      message={L.message}
      confirmLabel={L.leave}
      cancelLabel={L.stay}
      danger
      onConfirm={() => blocker.proceed()}
      onCancel={() => blocker.reset()}
    />
  );
}
