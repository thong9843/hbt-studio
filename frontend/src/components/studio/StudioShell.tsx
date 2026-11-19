import { useEffect, type ReactNode } from 'react';
import { useStudioWorkspace } from '../../hooks/studioWorkspace';
import { cx } from '../ui/cx';
import { SceneTimelineStrip, type SceneTimelineStripProps } from './SceneTimelineStrip';
import { StageCanvas, type StageCanvasProps } from './StageCanvas';
import { StudioTopBar, type StudioTopBarProps } from './StudioTopBar';

export interface StudioInspectorTab {
  id: string;
  label: string;
  icon?: ReactNode;
  badge?: string | number;
  content: ReactNode;
}

export interface StudioShellProps {
  topBar: StudioTopBarProps;
  tabs: StudioInspectorTab[];
  activeTab: string;
  onTabChange: (tabId: string) => void;
  inspectorHeader?: ReactNode;
  liveBanner?: ReactNode;
  canvas: StageCanvasProps;
  timeline?: SceneTimelineStripProps;
  modals?: ReactNode;
}

/**
 * Khung Không gian Dựng phim Hợp nhất (`StudioShell.tsx`, chuẩn VEED.IO Bright Minimalist):
 * - Tự động thu gọn Sidebar chính thành Icon Rail 60px khi vào Studio.
 * - Topbar 56px cực gọn + Cột công cụ trái chia 3–4 Tab sạch sẽ + Sân khấu Canvas trung tâm + Dải cảnh ngang ở đáy.
 */
export function StudioShell({
  topBar,
  tabs,
  activeTab,
  onTabChange,
  inspectorHeader,
  liveBanner,
  canvas,
  timeline,
  modals,
}: StudioShellProps) {
  const ws = useStudioWorkspace();
  const setStudioMode = ws?.setStudioMode;

  useEffect(() => {
    setStudioMode?.(true);
    return () => {
      setStudioMode?.(false);
    };
  }, [setStudioMode]);

  const currentTab = tabs.find((t) => t.id === activeTab) ?? tabs[0];

  return (
    <div className="flex min-h-screen flex-col bg-bg text-text">
      <StudioTopBar {...topBar} />

      {liveBanner && <div className="border-b border-line bg-card px-4 py-2.5">{liveBanner}</div>}

      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[440px_1fr]">
        {/* Cột công cụ trái (Tabbed Inspector: tại một thời điểm chỉ hiện duy nhất 1 nhóm chức năng) */}
        <aside
          aria-label="Bảng công cụ biên tập"
          className="flex flex-col border-b border-line bg-card lg:border-b-0 lg:border-r"
        >
          <div
            role="tablist"
            aria-label="Nhóm công cụ Studio"
            className="flex items-center gap-1 border-b border-line bg-soft px-3 py-2"
          >
            {tabs.map((tab) => {
              const isSelected = tab.id === currentTab?.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  aria-selected={isSelected}
                  onClick={() => onTabChange(tab.id)}
                  className={cx(
                    'inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg px-2.5 py-2 text-tiny font-bold transition-colors',
                    isSelected
                      ? 'bg-card text-brand shadow-card'
                      : 'text-muted hover:bg-card/60 hover:text-text',
                  )}
                >
                  {tab.icon}
                  <span className="truncate">{tab.label}</span>
                  {tab.badge !== undefined && (
                    <span
                      className={cx(
                        'rounded-pill px-1.5 py-0.2 text-[10px] font-extrabold tabular-nums',
                        isSelected
                          ? 'bg-[var(--accent-soft)] text-[var(--on-accent-soft)]'
                          : 'bg-soft-2 text-muted',
                      )}
                    >
                      {tab.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {inspectorHeader && (
            <div className="border-b border-line px-4 py-2.5">{inspectorHeader}</div>
          )}

          <div className="flex-1 space-y-4 overflow-y-auto p-4">{currentTab?.content}</div>
        </aside>

        {/* Sân khấu Xem trước trung tâm */}
        <StageCanvas {...canvas} />
      </div>

      {timeline && <SceneTimelineStrip {...timeline} />}
      {modals}
    </div>
  );
}
