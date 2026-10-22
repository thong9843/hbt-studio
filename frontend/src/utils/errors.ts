import { ApiError } from '../api/client';
import { vi } from '../i18n/vi';

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/** Lời gợi ý cách sửa theo loại lỗi (DESIGN-HBT.md mục 8: nói thẳng và gợi cách sửa). */
export function errorHint(error: unknown): string | null {
  const h = vi.errors.hints;
  if (error instanceof ApiError) {
    if (error.status === 503) return h.unavailable;
    if (error.status === 409) return h.busy;
    if (error.status === 413) return h.tooLarge;
    if (error.status === 404) return h.notFound;
    if (error.status === 422 || error.status === 400) return h.invalid;
    return null;
  }
  // fetch không tới được máy chủ
  if (error instanceof TypeError) return h.network;
  return null;
}

/** Nội dung hiển thị: thông báo lỗi kèm gợi ý nếu có. */
export function describeError(error: unknown): { message: string; hint: string | null } {
  const hint = errorHint(error);
  const message = error instanceof TypeError ? vi.common.unreachable : errorMessage(error);
  return { message, hint: error instanceof TypeError ? null : hint };
}
