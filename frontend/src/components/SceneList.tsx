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
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import type { Scene } from '../api/types';
import { projectFileUrl } from '../api/endpoints';
import { vi } from '../i18n/vi';
import { sceneNumber } from '../utils/scene';

interface Props {
  slug: string;
  scenes: Scene[];
  selected: number;
  imageVersion: number;
  disabled?: boolean;
  onSelect: (index: number) => void;
  /** `order[i]` = chỉ số cũ của cảnh mới thứ i. */
  onReorder: (order: number[], selectedAfter: number) => void;
}

function Row({
  id,
  index,
  scene,
  slug,
  active,
  imageVersion,
  onSelect,
}: {
  id: string;
  index: number;
  scene: Scene;
  slug: string;
  active: boolean;
  imageVersion: number;
  onSelect: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id,
  });
  const n = sceneNumber(index);
  const firstLine = scene.card.lines[0]?.text || scene.voice.slice(0, 40);
  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`flex items-center gap-3 rounded-2xl p-2 ${
        active ? 'bg-fg text-bg' : 'bg-surface'
      } ${isDragging ? 'z-10 opacity-80 shadow-lg' : ''}`}
    >
      <button
        type="button"
        aria-label={vi.compose.scenes.drag(n)}
        className="flex h-9 w-7 shrink-0 cursor-grab items-center justify-center rounded-lg text-lg leading-none opacity-70 hover:opacity-100"
        {...attributes}
        {...listeners}
      >
        ⋮⋮
      </button>
      <button
        type="button"
        onClick={onSelect}
        aria-current={active ? 'true' : undefined}
        className="flex min-w-0 flex-1 items-center gap-3 text-left"
      >
        <span className="h-16 w-9 shrink-0 overflow-hidden rounded-lg bg-surface-2">
          {scene.image ? (
            <img
              src={`${projectFileUrl(slug, scene.image)}?v=${imageVersion}`}
              alt=""
              className="h-full w-full object-cover"
              loading="lazy"
            />
          ) : null}
        </span>
        <span className="min-w-0">
          <span className="block text-xs font-extrabold uppercase tracking-wider">
            {vi.compose.scenes.scene(n)}
            {scene.punch && <span className="ml-2 chip chip-warn">{vi.compose.scenes.punch}</span>}
          </span>
          <span className="block truncate text-xs opacity-70">
            {scene.image ? firstLine : vi.compose.scenes.noImage}
          </span>
        </span>
      </button>
    </li>
  );
}

export function SceneList({
  slug,
  scenes,
  selected,
  imageVersion,
  disabled,
  onSelect,
  onReorder,
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

  return (
    <section aria-label={vi.compose.scenes.title}>
      <h2 className="mb-3 text-sm text-muted">{vi.compose.scenes.title}</h2>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={ids} strategy={verticalListSortingStrategy} disabled={disabled}>
          <ul className="space-y-2">
            {scenes.map((scene, i) => (
              <Row
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
    </section>
  );
}
