import { Outlet } from 'react-router-dom';
import { useMediaQuery } from '../hooks/useMediaQuery';
import { SideNav, type RenderProgress } from './SideNav';

/** Điểm gãy: từ 1280 px thanh trái đầy đủ, dưới đó chỉ còn biểu tượng (DESIGN-HBT.md mục 5). */
export const WIDE_QUERY = '(min-width: 1280px)';

interface Props {
  /** Tiến độ dựng đang chạy; chưa nối job thật (Đợt 3d). */
  render?: RenderProgress | null;
}

/** Khung bố cục: thanh trái cố định + vùng nội dung bên phải. */
export function AppShell({ render }: Props) {
  const wide = useMediaQuery(WIDE_QUERY);
  return (
    <div className="flex min-h-screen bg-bg">
      <SideNav mini={!wide} render={render} />
      <div className="min-w-0 flex-1">
        <Outlet />
      </div>
    </div>
  );
}
