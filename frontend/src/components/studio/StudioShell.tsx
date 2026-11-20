import { memo, type ReactNode } from 'react';
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

const TabPanelContent = memo(function TabPanelContent({
  tabId,
  content,
}: {
  tabId: string;
  content: ReactNode;
}) {
  return (
    <div key={tabId} role="tabpanel" className="ui-panel-fade space-y-3.5">
      {content}
    </div>
  );
});

/**
 * Khung Không gian Dựng phim Hợp nhất (`StudioShell.tsx`, chuẩn VEED.IO Bright Minimalist):
 * - Khóa khung ứng dụng `100vh` (`h-screen max-h-screen overflow-hidden`).
 * - Cột Inspector trái `376px` cuộn độc lập (`overflow-y-auto`), 4 tab chia đều không cắt chữ kèm thanh trượt mượt.
 * - Sân khấu Canvas căn giữa cố định, dải `SceneTimelineStrip` (cao `76px`) luôn ghim chắc ở đáy màn hình.
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
  const activeIdx = Math.max(
    0,
    tabs.findIndex((t) => t.id === activeTab),
  );
  const currentTab = tabs[activeIdx] ?? tabs[0];
  const tabCount = Math.max(1, tabs.length);

  return (
    <div className="flex h-screen max-h-screen flex-col overflow-hidden bg-bg text-text">
      <StudioTopBar {...topBar} />

      {liveBanner && (
        <div className="shrink-0 border-b border-line bg-card px-4 py-2">{liveBanner}</div>
      )}

      <div className="grid min-h-0 flex-1 grid-cols-1 overflow-hidden lg:grid-cols-[376px_1fr]">
        {/* Cột công cụ trái (376px, cuộn độc lập, 4 tab chia đều min-w-0 không cắt chữ) */}
        <aside
          aria-label="Bảng công cụ biên tập"
          className="flex min-h-0 flex-col overflow-hidden border-b border-line bg-card lg:border-b-0 lg:border-r"
        >
          <div
            role="tablist"
            aria-label="Nhóm công cụ Studio"
            className="relative grid shrink-0 border-b border-line bg-soft px-1.5 pt-1.5 pb-1"
            style={{ gridTemplateColumns: `repeat(${tabCount}, minmax(0, 1fr))` }}
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
                    'inline-flex min-w-0 items-center justify-center gap-1 rounded-lg px-1 py-2 text-[11.5px] font-bold whitespace-nowrap transition-colors',
                    isSelected
                      ? 'bg-card text-brand shadow-card'
                      : 'text-muted hover:bg-card/60 hover:text-text',
                  )}
                >
                  <span className="shrink-0">{tab.icon}</span>
                  <span className="min-w-0 truncate">{tab.label}</span>
                  {tab.badge !== undefined && (
                    <span
                      className={cx(
                        'shrink-0 rounded-pill px-1.5 py-0.2 text-[10px] font-extrabold tabular-nums',
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
            {/* Thanh chỉ báo trượt mượt dưới tab đang chọn */}
            <span
              aria-hidden="true"
              className="pointer-events-none absolute bottom-0 left-1.5 right-1.5 h-[2px] overflow-hidden"
            >
              <span
                className="block h-full rounded-full bg-brand transition-transform duration-150 motion-reduce:transition-none"
                style={{
                  width: `${100 / tabCount}%`,
                  transform: `translateX(${activeIdx * 100}%)`,
                }}
              />
            </span>
          </div>

          {inspectorHeader && (
            <div className="shrink-0 border-b border-line px-3.5 py-2">{inspectorHeader}</div>
          )}

          <div className="min-h-0 flex-1 overflow-y-auto p-3.5">
            {currentTab && <TabPanelContent tabId={currentTab.id} content={currentTab.content} />}
          </div>
        </aside>

        {/* Sân khấu Xem trước trung tâm */}
        <StageCanvas {...canvas} className="min-h-0 overflow-hidden" />
      </div>

      {timeline && <SceneTimelineStrip {...timeline} />}
      {modals}
    </div>
  );
}
