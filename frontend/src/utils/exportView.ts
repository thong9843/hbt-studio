import type { LintResult, RenderRecord } from '../api/types';
import { vi } from '../i18n/vi';

export type CheckStatus = 'ready' | 'warn' | 'blocked';

/** Trạng thái chung của thẻ Kiểm tra: bị chặn > có cảnh báo > sẵn sàng; `null` khi chưa biết. */
export function checkStatus(lint: LintResult | undefined, missing: string[]): CheckStatus | null {
  if (!lint) return missing.length > 0 ? 'blocked' : null;
  if (lint.blocked || lint.problems.length > 0 || missing.length > 0) return 'blocked';
  return lint.counts.warn > 0 ? 'warn' : 'ready';
}

/** Nhãn lần dựng ở lịch sử: Bản đẹp / Xem nhanh / Xem nhanh n giây đầu. */
export function historyLabel(r: Pick<RenderRecord, 'preview' | 'preview_seconds'>): string {
  const H = vi.export.history;
  if (!r.preview) return H.final;
  return r.preview_seconds ? H.fastHead(r.preview_seconds) : H.fast;
}
