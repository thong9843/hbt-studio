import { memo } from 'react';
import { vi } from '../../i18n/vi';
import { PlusIcon, TrashIcon } from '../icons';
import { cx } from '../ui/cx';

export interface TimelineSceneItem {
  id: string;
  index: number;
  title?: string;
  summary: string;
  badge?: string;
  durationSec?: number;
}

export interface SceneTimelineStripProps {
  items: TimelineSceneItem[];
  selectedId: string;
  onSelect: (id: string) => void;
  onAdd?: () => void;
  addLabel?: string;
  onDelete?: (id: string) => void;
  totalDurationSec?: number;
}

const TimelineCard = memo(function TimelineCard({
  item,
  selected,
  canDelete,
  onSelect,
  onDelete,
}: {
  item: TimelineSceneItem;
  selected: boolean;
  canDelete: boolean;
  onSelect: (id: string) => void;
  onDelete?: (id: string) => void;
}) {
  return (
    <div
      role="button"
      tabIndex={0}
      aria-current={selected ? 'true' : undefined}
      onClick={() => onSelect(item.id)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSelect(item.id);
        }
      }}
      className={cx(
        'group relative flex h-[84px] w-[176px] shrink-0 cursor-pointer flex-col justify-between rounded-inner border px-3 py-2.5 text-left transition-colors',
        selected ? 'border-brand bg-[var(--accent-soft)]' : 'border-line bg-card hover:bg-soft',
      )}
    >
      <div className="flex items-center justify-between gap-1.5">
        <div className="flex min-w-0 items-center gap-1.5">
          <span
            className={cx(
              'inline-flex h-5 min-w-[24px] shrink-0 items-center justify-center rounded px-1.5 text-[11px] font-extrabold tabular-nums',
              selected ? 'bg-brand text-white' : 'bg-soft text-text-2',
            )}
          >
            #{item.index}
          </span>
          {item.durationSec !== undefined && (
            <span className="shrink-0 text-[11px] font-semibold text-muted tabular-nums">
              · {item.durationSec.toFixed(1)}s
            </span>
          )}
          {item.badge && (
            <span className="truncate rounded bg-soft px-1.5 py-0.5 text-[10px] font-semibold text-muted">
              {item.badge}
            </span>
          )}
        </div>
        {selected && canDelete && onDelete && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onDelete(item.id);
            }}
            aria-label={`Xóa cảnh #${item.index}`}
            title={`Xóa cảnh #${item.index}`}
            className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded text-muted hover:bg-danger-soft hover:text-danger"
          >
            <TrashIcon size={12} />
          </button>
        )}
      </div>

      <p className="w-full truncate text-[12px] font-medium leading-5 text-text">
        {item.summary || item.title || 'Chưa có lời thoại…'}
      </p>
    </div>
  );
});

/**
 * Dải phân cảnh ngang ở đáy Studio (`SceneTimelineStrip`, cao cố định 76px chuẩn VEED.IO).
 * Luôn ghim chắc chắn ở đáy màn hình 100vh, không bao giờ bị đẩy khuất khỏi viewport.
 */
export function SceneTimelineStrip({
  items,
  selectedId,
  onSelect,
  onAdd,
  addLabel = vi.studioShell.timelineAddScene,
  onDelete,
  totalDurationSec,
}: SceneTimelineStripProps) {
  return (
    <footer
      aria-label={vi.studioShell.timelineTitle}
      className="flex h-[116px] shrink-0 flex-col justify-center border-t border-line bg-card px-3.5 py-2"
    >
      <div className="mb-1.5 flex items-center justify-between gap-2 leading-none">
        <span className="text-[10px] font-bold uppercase tracking-wider text-muted">
          {vi.studioShell.timelineTitle} ({items.length})
        </span>
        {totalDurationSec !== undefined && (
          <span className="text-[10px] font-semibold text-muted tabular-nums">
            ≈ {totalDurationSec.toFixed(1)}s
          </span>
        )}
      </div>
      <div className="flex items-center gap-2 overflow-x-auto pb-0.5">
        {items.map((item) => (
          <TimelineCard
            key={item.id}
            item={item}
            selected={item.id === selectedId}
            canDelete={items.length > 1}
            onSelect={onSelect}
            onDelete={onDelete}
          />
        ))}
        {onAdd && (
          <button
            type="button"
            onClick={onAdd}
            className="flex h-[84px] shrink-0 items-center gap-1 rounded-inner border border-dashed border-line-input bg-soft px-3.5 text-tiny font-bold text-text-2 transition-colors hover:border-brand hover:text-brand"
          >
            <PlusIcon size={13} />
            {addLabel}
          </button>
        )}
      </div>
    </footer>
  );
}
