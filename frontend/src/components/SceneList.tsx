import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  arrayMove,
  horizontalListSortingStrategy,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { projectFileUrl } from '../api/endpoints';
import type { Scene } from '../api/types';
import { vi } from '../i18n/vi';
import { MAX_SCENES, MIN_SCENES } from '../utils/limits';
import { sceneNumber } from '../utils/scene';
import { GripIcon, PlusIcon, TrashIcon } from './icons';

interface ItemProps {
  id: string;
  index: number;
  scene: Scene;
  slug: string;
  active: boolean;
  imageVersion: number;
  onSelect: () => void;
}

/** Một mục cảnh cao 72: ảnh vuông 56, số cảnh, một dòng lời đọc cắt bớt, tay nắm kéo 6 chấm. */
export function SceneItem({ id, index, scene, slug, active, imageVersion, onSelect }: ItemProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id,
  });
  const n = sceneNumber(index);
  const excerpt = scene.voice.replace(/[|{}]/g, '').trim();
  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`flex h-18 shrink-0 items-center gap-1 rounded-card border-2 bg-surface pr-3 ${
        active ? 'border-accent' : 'border-transparent'
      } ${isDragging ? 'z-10 opacity-80 shadow-lg' : ''}`}
    >
      <button
        type="button"
        aria-label={vi.compose.scenes.drag(n)}
        className="flex h-11 w-9 shrink-0 cursor-grab items-center justify-center rounded-full text-text-muted hover:text-text"
        {...attributes}
        {...listeners}
      >
        <GripIcon />
      </button>
      <button
        type="button"
        onClick={onSelect}
        aria-current={active ? 'true' : undefined}
        className="flex h-full min-w-0 flex-1 items-center gap-3 text-left"
      >
        <span className="h-14 w-14 shrink-0 overflow-hidden rounded-preview bg-surface-2">
          {scene.image && (
            <img
              src={`${projectFileUrl(slug, scene.image)}?v=${imageVersion}`}
              alt=""
              className="h-full w-full object-cover"
              loading="lazy"
            />
          )}
        </span>
        <span className="min-w-0">
          <span className="flex items-center gap-2 text-tiny font-semibold uppercase">
            {vi.compose.scenes.scene(n)}
            {scene.punch && <span className="chip chip-warn">{vi.compose.scenes.punch}</span>}
          </span>
          <span className="block truncate text-small text-text-muted">
            {scene.image ? excerpt || vi.compose.scenes.noVoice : vi.compose.scenes.noImage}
          </span>
        </span>
      </button>
    </li>
  );
}

interface Props {
  slug: string;
  scenes: Scene[];
  selected: number;
  imageVersion: number;
  disabled?: boolean;
  /** Bố cục ngang (màn 1024–1279 px): danh sách cuộn ngang trên đầu. */
  horizontal?: boolean;
  onSelect: (index: number) => void;
  /** `order[i]` = chỉ số cũ của cảnh mới thứ i. */
  onReorder: (order: number[], selectedAfter: number) => void;
  onAdd: () => void;
  onRemove: (index: number) => void;
}

export function SceneList({
  slug,
  scenes,
  selected,
  imageVersion,
  disabled,
  horizontal,
  onSelect,
  onReorder,
  onAdd,
  onRemove,
}: Props) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const ids = scenes.map((_, i) => `scene-${i}`);

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const from = ids.indexOf(String(active.id));
    const to = ids.indexOf(String(over.id));
    if (from < 0 || to < 0) return;
    const order = arrayMove(
      scenes.map((_, i) => i),
      from,
      to,
    );
    onReorder(order, order.indexOf(selected));
  };

  const full = scenes.length >= MAX_SCENES;
  const atMin = scenes.length <= MIN_SCENES;
  return (
    <section aria-label={vi.compose.scenes.title}>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-tiny font-semibold uppercase text-text-muted">
          {vi.compose.scenes.title} · <span className="num">{scenes.length}</span>
        </h2>
      </div>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext
          items={ids}
          strategy={horizontal ? horizontalListSortingStrategy : verticalListSortingStrategy}
          disabled={disabled}
        >
          <ul className={horizontal ? 'flex gap-2 overflow-x-auto pb-2' : 'space-y-2'}>
            {scenes.map((scene, i) => (
              <SceneItem
                key={ids[i]}
                id={ids[i]}
                index={i}
                scene={scene}
                slug={slug}
                active={i === selected}
                imageVersion={imageVersion}
                onSelect={() => onSelect(i)}
              />
            ))}
          </ul>
        </SortableContext>
      </DndContext>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          disabled={full || disabled}
          title={full ? vi.compose.scenes.max : undefined}
          onClick={onAdd}
        >
          <PlusIcon size={18} />
          {vi.compose.scenes.add}
        </button>
        <button
          type="button"
          className="btn btn-danger btn-sm"
          disabled={atMin || disabled}
          title={atMin ? vi.compose.scenes.min : undefined}
          onClick={() => onRemove(selected)}
        >
          <TrashIcon size={18} />
          {vi.compose.scenes.remove}
        </button>
      </div>
    </section>
  );
}
