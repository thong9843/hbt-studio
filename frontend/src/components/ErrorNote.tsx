import { vi } from '../i18n/vi';
import { errorMessage } from '../utils/errors';

/** Thông báo lỗi nhỏ, đọc được bằng trình đọc màn hình. */
export function ErrorNote({ error, className = '' }: { error: unknown; className?: string }) {
  if (!error) return null;
  return (
    <p
      role="alert"
      className={`rounded-xl bg-danger-bg px-4 py-2 text-sm font-bold text-danger ${className}`}
    >
      {vi.common.errorPrefix} {errorMessage(error)}
    </p>
  );
}
