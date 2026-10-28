import { Outlet } from 'react-router-dom';
import { useRenderJob } from '../hooks/renderJob';
import { useMediaQuery } from '../hooks/useMediaQuery';
import { useRemainingText } from '../hooks/useRemaining';
import { NewProjectProvider } from './NewProjectDialog';
import { RenderJobProvider } from './RenderJobProvider';
import { SideNav, type RenderProgress } from './SideNav';

/** Điểm gãy: từ 1280 px thanh trái đầy đủ, dưới đó chỉ còn biểu tượng (DESIGN-HBT.md mục 5). */
export const WIDE_QUERY = '(min-width: 1280px)';

interface Props {
  /** Ghi đè tiến độ lấy từ job thật (dùng trong test); bỏ trống thì đọc `RenderJobProvider`. */
  render?: RenderProgress | null;
}

/** Thanh trái nhận tiến độ từ job toàn cục (`undefined` = lấy từ context). */
function Nav({ mini, render }: { mini: boolean; render?: RenderProgress | null }) {
  const job = useRenderJob();
  const remaining = useRemainingText();
  const fromJob: RenderProgress | null = job.running
    ? {
        percent: job.percent,
        step: job.step,
        remaining: remaining ?? undefined,
        onCancel: () => void job.cancel(),
      }
    : null;
  return <SideNav mini={mini} render={render === undefined ? fromJob : render} />;
}

/** Khung bố cục: thanh trái cố định + vùng nội dung bên phải. */
export function AppShell({ render }: Props) {
  const wide = useMediaQuery(WIDE_QUERY);
  return (
    <NewProjectProvider>
      <RenderJobProvider>
        <div className="flex min-h-screen bg-bg">
          <Nav mini={!wide} render={render} />
          <div className="min-w-0 flex-1">
            <Outlet />
          </div>
        </div>
      </RenderJobProvider>
    </NewProjectProvider>
  );
}
