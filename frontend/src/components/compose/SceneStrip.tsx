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
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import type { KeyboardEventHandler, PointerEventHandler } from 'react';
import { useDropzone } from 'react-dropzone';
import { projectFileUrl } from '../../api/endpoints';
import type { Scene } from '../../api/types';
import { vi } from '../../i18n/vi';
import { MAX_SCENES } from '../../utils/limits';
import { sceneNumber } from '../../utils/scene';
import { GripIcon, ImageIcon, PlusIcon } from '../icons';
import { Button } from '../ui/Button';
import { cx } from '../ui/cx';

const T = vi.compose.strip;
const IMAGE_ACCEPT = { 'image/png': [], 'image/jpeg': [], 'image/webp': [] };

interface ItemProps {
  id: string;
  index: number;
  scene: Scene;
  slug: string;
  active: boolean;
  imageVersion: number;
  onSelect: () => void;
}

/** Một thẻ cảnh ở dải: ảnh 54×96, số cảnh, tay nắm kéo. Kéo được cả bằng bàn phím (tay nắm). */
export function SceneItem({ id, index, scene, slug, active, imageVersion, onSelect }: ItemProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    setActivatorNodeRef,
    transform,
    transition,
    isDragging,
    isOver,
  } = useSortable({ id });
  const n = sceneNumber(index);
  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className="relative shrink-0"
    >
      <button
        type="button"
        onClick={onSelect}
        aria-current={active ? 'true' : undefined}
        aria-label={`${T.sceneLabel(n)}${scene.image ? '' : ` — ${T.noImage.toLowerCase()}`}`}
        className="ui-scene"
        data-over={(isOver && !isDragging) || undefined}
        data-dragging={isDragging || undefined}
        onPointerDown={
          listeners?.onPointerDown as PointerEventHandler<HTMLButtonElement> | undefined
        }
      >
        <span className="ui-scene-img">
          {scene.image ? (
            <img
              src={`${projectFileUrl(slug, scene.image)}?v=${imageVersion}`}
              alt=""
              className="h-full w-full object-cover"
              loading="lazy"
              decoding="async"
            />
          ) : (
            <ImageIcon size={20} />
          )}
        </span>
        <span className="ui-scene-no" aria-hidden="true">
          {n}
        </span>
      </button>
      <button
        type="button"
        ref={setActivatorNodeRef}
        aria-label={T.drag(n)}
        className="ui-scene-grip"
        {...attributes}
        onKeyDown={listeners?.onKeyDown as KeyboardEventHandler<HTMLButtonElement> | undefined}
      >
        <GripIcon size={14} />
      </button>
    </li>
  );
}

interface Props {
  slug: string;
  scenes: Scene[];
  selected: number;
  imageVersion: number;
  /** Đang bận (đổi thứ tự / tải ảnh): khoá kéo và thêm. */
  disabled?: boolean;
  /** Đang tải ảnh hàng loạt: `done/total`. */
  progress?: { done: number; total: number } | null;
  onSelect: (index: number) => void;
  /** `order[i]` = chỉ số cũ của cảnh mới thứ i. */
  onReorder: (order: number[], selectedAfter: number) => void;
  onAdd: () => void;
  onDropFiles: (files: File[]) => void;
}

/** Dải cảnh ngang: kéo đổi thứ tự, nút +, và vùng thả nhiều ảnh (13.B2.1). */
export function SceneStrip({
  slug,
  scenes,
  selected,
  imageVersion,
  disabled,
  progress,
  onSelect,
  onReorder,
  onAdd,
  onDropFiles,
}: Props) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const ids = scenes.map((_, i) => `scene-${i}`);

  const { getRootProps, getInputProps, isDragActive, open, fileRejections } = useDropzone({
    onDrop: (files) => files.length > 0 && onDropFiles(files),
    accept: IMAGE_ACCEPT,
    multiple: true,
    noClick: true,
    noKeyboard: true,
    disabled,
  });

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
  return (
    <section aria-label={vi.compose.scenes.title}>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-h2 font-bold">
          {vi.compose.scenes.title} · <span className="tabular-nums">{scenes.length}</span>
        </h2>
        <div className="flex items-center gap-3">
          <span role="status" className="text-small text-muted tabular-nums">
            {progress ? T.uploading(progress.done, progress.total) : ''}
          </span>
          <Button
            tone="soft"
            size="sm"
            icon={<ImageIcon size={18} />}
            disabled={disabled}
            onClick={open}
            title={T.dropHint}
          >
            {T.addImages}
          </Button>
        </div>
      </div>
      <div {...getRootProps({ className: cx('ui-strip', 'bg-soft-2') })} data-active={isDragActive}>
        <input {...getInputProps({ 'aria-label': T.addImages })} />
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <SortableContext items={ids} strategy={horizontalListSortingStrategy} disabled={disabled}>
            <ul className="flex gap-2">
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
        <button
          type="button"
          className="ui-scene-add"
          aria-label={T.add}
          title={full ? vi.compose.scenes.max : T.add}
          disabled={full || disabled}
          onClick={onAdd}
        >
          <PlusIcon size={22} />
        </button>
        {isDragActive && (
          <p className="self-center whitespace-nowrap px-3 text-small font-bold">{T.dropActive}</p>
        )}
      </div>
      {fileRejections.length > 0 && (
        <p role="alert" className="mt-2 text-small font-bold text-danger">
          {T.rejected}
        </p>
      )}
    </section>
  );
}
