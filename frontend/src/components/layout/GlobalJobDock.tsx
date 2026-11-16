import { useRenderJob } from '../../hooks/renderJob';
import { useRemainingText } from '../../hooks/useRemaining';
import { vi } from '../../i18n/vi';
import { StopIcon } from '../icons';
import { Button } from '../ui/Button';
import { Progress } from '../ui/Progress';

/**
 * Thanh Tiến trình Dựng Toàn cục (Global SSE Job Dock):
 * Nổi gọn ở góc dưới bên phải, luôn theo sát người dùng khi chuyển giữa các trang.
 * Dữ liệu lấy trực tiếp từ RenderJobProvider (GET /api/jobs + SSE /api/jobs/{id}/events).
 */
export function GlobalJobDock() {
  const job = useRenderJob();
  const remaining = useRemainingText();

  if (!job.running) return null;

  const pct = Math.max(0, Math.min(100, Math.round(job.percent)));

  return (
    <aside
      aria-label="Tiến trình dựng toàn cục"
      className="fixed bottom-5 right-5 z-30 w-[340px] max-w-[calc(100vw-2rem)] rounded-card border border-line bg-card/95 p-4 shadow-pop backdrop-blur-md"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="relative flex h-2.5 w-2.5 shrink-0">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-engine-postv opacity-75" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-engine-postv" />
            </span>
            <span className="truncate text-tiny font-bold uppercase tracking-wider text-muted">
              {vi.nav.renderProgress}
              {job.slug ? ` · ${job.slug}` : ''}
            </span>
          </div>
          <p className="mt-1 truncate text-small font-bold text-text">
            <span className="num mr-1.5 text-engine-postv">{pct}%</span>
            <span>{job.step || 'Đang xử lý...'}</span>
          </p>
        </div>
        <Button
          tone="soft"
          size="sm"
          onClick={() => void job.cancel()}
          icon={<StopIcon size={14} />}
          aria-label="Hủy dựng toàn cục"
          title={vi.nav.cancelRender}
        >
          Dừng
        </Button>
      </div>

      <div className="mt-3">
        <Progress value={pct} label={vi.nav.renderProgressBar} />
      </div>

      {remaining && (
        <p className="mt-2 text-right text-tiny font-medium text-muted tabular-nums">{remaining}</p>
      )}
    </aside>
  );
}
