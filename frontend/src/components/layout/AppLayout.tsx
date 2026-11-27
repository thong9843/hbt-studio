import { useCallback, useState } from 'react';
import { Outlet } from 'react-router-dom';
import {
  inferJobEngine,
  resolveJobRoute,
  useRenderJobProgress,
  useRenderJobStatus,
} from '../../hooks/renderJob';
import { useMediaQuery } from '../../hooks/useMediaQuery';
import { useRemainingText } from '../../hooks/useRemaining';
import { NewProjectProvider } from '../NewProjectDialog';
import { RenderJobProvider } from '../RenderJobProvider';
import {
  Sidebar,
  SIDEBAR_COLLAPSED_KEY,
  SidebarRenderStatus,
  type RenderProgress,
} from './Sidebar';
import { StudioWorkspaceProvider } from './StudioWorkspaceContext';

/** Điểm gãy: từ 1280 px thanh trái mặc định mở rộng (224px), dưới đó mặc định thu gọn (64px). */
export const WIDE_QUERY = '(min-width: 1280px)';

export interface AppLayoutProps {
  /** Ghi đè tiến độ lấy từ job thật (dùng trong test); bỏ trống thì đọc `RenderJobProvider`. */
  render?: RenderProgress | null;
}

function readStoredSidebarCollapsed(): boolean | null {
  try {
    const raw = localStorage.getItem(SIDEBAR_COLLAPSED_KEY);
    if (raw === 'true') return true;
    if (raw === 'false') return false;
    return null;
  } catch {
    return null;
  }
}

/** Cô lập đăng ký tiến độ % riêng cho SidebarRenderStatus để Sidebar/Layout re-render 0 lần khi % nhảy. */
function LiveSidebarRenderCard({ mini }: { mini: boolean }) {
  const status = useRenderJobStatus();
  const progress = useRenderJobProgress();
  const remaining = useRemainingText();
  if (!status.running) return null;
  const engine = inferJobEngine(status.kind, status.engine);
  const route = resolveJobRoute(engine, status.kind, status.slug, status.route);
  return (
    <SidebarRenderStatus
      mini={mini}
      render={{
        percent: progress.percent,
        step: progress.stage || progress.step,
        engine,
        title: status.title || status.slug || undefined,
        route,
        remaining: remaining ?? undefined,
        onCancel: () => void status.cancel(),
      }}
    />
  );
}

/**
 * Thanh trái nhận tiến độ tổng từ job toàn cục (luôn hiển thị xuyên suốt mọi route cho cả 4 động cơ).
 */
function Nav({ defaultMini, render }: { defaultMini: boolean; render?: RenderProgress | null }) {
  const status = useRenderJobStatus();
  const [userCollapsed, setUserCollapsed] = useState<boolean | null>(() =>
    readStoredSidebarCollapsed(),
  );

  const mini = userCollapsed ?? defaultMini;

  const handleToggleMini = useCallback(() => {
    setUserCollapsed((prev) => {
      const next = !(prev ?? defaultMini);
      try {
        localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(next));
      } catch {
        // Bỏ qua lỗi khi trình duyệt chặn localStorage
      }
      return next;
    });
  }, [defaultMini]);

  const showLiveCard = render === undefined && status.running;

  return (
    <Sidebar
      mini={mini}
      onToggleMini={handleToggleMini}
      render={render}
      renderSlot={showLiveCard ? <LiveSidebarRenderCard mini={mini} /> : undefined}
    />
  );
}

/**
 * Khung bố cục tổng thể Unified Studio UI:
 * Sidebar cố định bên trái (chứa nút mở/thu gọn & SidebarRenderStatus duy nhất) + Main Workspace bên phải.
 */
export function AppLayout({ render }: AppLayoutProps) {
  const wide = useMediaQuery(WIDE_QUERY);
  return (
    <NewProjectProvider>
      <RenderJobProvider>
        <StudioWorkspaceProvider>
          <div className="flex min-h-screen bg-bg text-text">
            <Nav defaultMini={!wide} render={render} />
            <div className="min-w-0 flex-1">
              <Outlet />
            </div>
          </div>
        </StudioWorkspaceProvider>
      </RenderJobProvider>
    </NewProjectProvider>
  );
}
