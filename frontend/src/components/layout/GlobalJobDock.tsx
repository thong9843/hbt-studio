import { Link, useLocation } from 'react-router-dom';
import { isOnActiveJobPage, useRenderJobProgress, useRenderJobStatus } from '../../hooks/renderJob';
import { useRemainingText } from '../../hooks/useRemaining';
import { vi } from '../../i18n/vi';
import { StopIcon } from '../icons';
import { Button } from '../ui/Button';
import { Progress } from '../ui/Progress';

/**
 * Thanh Tiến trình Dựng Toàn cục (Global SSE Job Dock):
 * - Chỉ hiện khi người dùng rời sang trang khác (vd `/`, `/library`, `/core`...) trong lúc job đang chạy ngầm.
 * - Tự động ẩn khi người dùng đang đứng ở đúng trang của job active (vd `/stickv`), triệt tiêu lỗi hiện 3 thanh tiến độ trùng lặp.
 * - Đăng ký `useRenderJobProgress` độc lập qua `useSyncExternalStore`, không làm re-render các trang khác.
 */
export function GlobalJobDock() {
  const status = useRenderJobStatus();
  const progress = useRenderJobProgress();
  const remaining = useRemainingText();
  const location = useLocation();

  if (!status.running) return null;
  if (isOnActiveJobPage(location.pathname, status.kind, status.slug)) return null;

  const pct = Math.max(0, Math.min(100, Math.round(progress.percent)));
  const isStickv = status.kind === 'stickv';
  const stageLabel = progress.stage || progress.step || vi.stickvJob.working;
  const stickvHref = status.slug ? `/stickv?slug=${encodeURIComponent(status.slug)}` : '/stickv';

  return (
    <aside
      aria-label="Tiến trình dựng toàn cục"
      className="fixed bottom-5 right-5 z-30 w-[356px] max-w-[calc(100vw-2rem)] rounded-card border border-line bg-card p-4 shadow-pop"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span
              className="inline-flex h-2.5 w-2.5 shrink-0 rounded-full bg-brand"
              aria-hidden="true"
            />
            <span className="truncate text-tiny font-bold uppercase tracking-wider text-muted">
              {isStickv ? vi.stickvJob.dockTitle : vi.nav.renderProgress}
              {status.slug ? ` · ${status.slug}` : ''}
            </span>
          </div>
          <p className="mt-1 truncate text-small font-bold text-text">
            <span className="num mr-1.5 text-brand">{pct}%</span>
            <span>{stageLabel}</span>
          </p>
          {isStickv &&
            progress.totalBeats != null &&
            progress.totalBeats > 0 &&
            progress.currentBeat != null && (
              <p className="mt-0.5 text-tiny font-semibold text-muted tabular-nums">
                {vi.stickvJob.beatProgress(progress.currentBeat, progress.totalBeats)}
              </p>
            )}
        </div>
        <Button
          tone="soft"
          size="sm"
          onClick={() => void status.cancel()}
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

      <div className="mt-2.5 flex items-center justify-between gap-2">
        {isStickv ? (
          <Link
            to={stickvHref}
            className="inline-flex items-center rounded-lg border border-line bg-soft px-2.5 py-1 text-tiny font-bold text-text transition-colors hover:bg-soft-2"
          >
            {vi.stickvJob.dockOpenStickv} →
          </Link>
        ) : (
          <span className="truncate text-tiny text-muted">{progress.message || ''}</span>
        )}
        {remaining && (
          <p className="shrink-0 text-right text-tiny font-medium text-muted tabular-nums">
            {remaining}
          </p>
        )}
      </div>
    </aside>
  );
}
