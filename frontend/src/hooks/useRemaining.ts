import { vi } from '../i18n/vi';
import { formatEstimate, remainingSeconds } from '../utils/estimate';
import { useRenderJob } from './renderJob';

/** "Còn ≈ …" của job đang chạy; "Đang ước tính…" khi tiến độ còn 0%; `null` khi không có job. */
export function useRemainingText(): string | null {
  const job = useRenderJob();
  if (!job.running) return null;
  const left =
    job.estimateSeconds === null ? null : remainingSeconds(job.estimateSeconds, job.percent);
  return left === null ? vi.estimate.waiting : vi.estimate.remaining(formatEstimate(left));
}
