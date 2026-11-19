import { vi } from '../i18n/vi';
import { formatEstimate, remainingSeconds } from '../utils/estimate';
import { useRenderJobProgress, useRenderJobStatus } from './renderJob';

/** "Còn ≈ …" của job đang chạy; "Đang ước tính…" khi tiến độ còn 0%; `null` khi không có job. */
export function useRemainingText(): string | null {
  const status = useRenderJobStatus();
  const progress = useRenderJobProgress();
  if (!status.running) return null;
  const left =
    status.estimateSeconds === null
      ? null
      : remainingSeconds(status.estimateSeconds, progress.percent);
  return left === null ? vi.estimate.waiting : vi.estimate.remaining(formatEstimate(left));
}
