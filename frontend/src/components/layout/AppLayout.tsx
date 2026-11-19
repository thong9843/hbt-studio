import { Outlet } from 'react-router-dom';
import { useRenderJob } from '../../hooks/renderJob';
import { useMediaQuery } from '../../hooks/useMediaQuery';
import { useRemainingText } from '../../hooks/useRemaining';
import { useStudioWorkspace } from '../../hooks/studioWorkspace';
import { NewProjectProvider } from '../NewProjectDialog';
import { RenderJobProvider } from '../RenderJobProvider';
import { Sidebar, type RenderProgress } from './Sidebar';
import { GlobalJobDock } from './GlobalJobDock';
import { StudioWorkspaceProvider } from './StudioWorkspaceContext';

/** Điểm gãy: từ 1280 px thanh trái đầy đủ, dưới đó chỉ còn biểu tượng. */
export const WIDE_QUERY = '(min-width: 1280px)';

export interface AppLayoutProps {
  /** Ghi đè tiến độ lấy từ job thật (dùng trong test); bỏ trống thì đọc `RenderJobProvider`. */
  render?: RenderProgress | null;
}

/** Thanh trái nhận tiến độ từ job toàn cục và tự thu thành Icon Rail khi ở trong StudioShell. */
function Nav({ mini, render }: { mini: boolean; render?: RenderProgress | null }) {
  const job = useRenderJob();
  const remaining = useRemainingText();
  const ws = useStudioWorkspace();
  const fromJob: RenderProgress | null = job.running
    ? {
        percent: job.percent,
        step: job.step,
        remaining: remaining ?? undefined,
        onCancel: () => void job.cancel(),
      }
    : null;
  return (
    <Sidebar
      mini={mini || Boolean(ws?.studioMode)}
      render={render === undefined ? fromJob : render}
    />
  );
}

/**
 * Khung bố cục tổng thể Unified Studio UI:
 * Sidebar cố định bên trái + Main Workspace bên phải tự co giãn mượt mà,
 * bọc trong StudioWorkspaceProvider để giữ trạng thái nhập liệu xuyên suốt các phân hệ.
 */
export function AppLayout({ render }: AppLayoutProps) {
  const wide = useMediaQuery(WIDE_QUERY);
  return (
    <NewProjectProvider>
      <RenderJobProvider>
        <StudioWorkspaceProvider>
          <div className="flex min-h-screen bg-bg text-text">
            <Nav mini={!wide} render={render} />
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
