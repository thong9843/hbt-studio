import { useCallback, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { useRenderJobProgress, useRenderJobStatus } from '../../hooks/renderJob';
import { useMediaQuery } from '../../hooks/useMediaQuery';
import { useRemainingText } from '../../hooks/useRemaining';
import { NewProjectProvider } from '../NewProjectDialog';
import { RenderJobProvider } from '../RenderJobProvider';
import { GlobalJobDock } from './GlobalJobDock';
import { Sidebar, SIDEBAR_COLLAPSED_KEY, type RenderProgress } from './Sidebar';
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

/**
 * Thanh trái nhận tiến độ từ job toàn cục và cho phép người dùng chủ động mở rộng / thu gọn
 * trên mọi trang (không còn ép khóa cứng ở các trang Studio).
 */
function Nav({
  defaultMini,
  render,
}: {
  defaultMini: boolean;
  render?: RenderProgress | null;
}) {
  const status = useRenderJobStatus();
  const progress = useRenderJobProgress();
  const remaining = useRemainingText();
  const location = useLocation();
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

  // Khi đang ở trang /stickv và StickV đang chạy, nút Xuất video trên Topbar đã hiện tiến độ -> không lặp lại ở Sidebar
  const hideSidebarProgressForActiveStudio =
    status.running && status.kind === 'stickv' && location.pathname.startsWith('/stickv');

  const fromJob: RenderProgress | null =
    status.running && !hideSidebarProgressForActiveStudio
      ? {
          percent: progress.percent,
          step: progress.step,
          remaining: remaining ?? undefined,
          onCancel: () => void status.cancel(),
        }
      : null;

  return (
    <Sidebar
      mini={mini}
      onToggleMini={handleToggleMini}
      render={render === undefined ? fromJob : render}
    />
  );
}

/**
 * Khung bố cục tổng thể Unified Studio UI:
 * Sidebar cố định bên trái (có nút đóng/mở linh hoạt) + Main Workspace bên phải tự co giãn mượt mà.
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
            <GlobalJobDock />
          </div>
        </StudioWorkspaceProvider>
      </RenderJobProvider>
    </NewProjectProvider>
  );
}
