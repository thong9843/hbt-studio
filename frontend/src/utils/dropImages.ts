import { MAX_SCENES } from './limits';

const collator = new Intl.Collator('en', { numeric: true, sensitivity: 'base' });

/** So tên file kiểu tự nhiên: `scene-2` đứng trước `scene-10`. Trùng thì so tên nguyên văn. */
export function compareNatural(a: string, b: string): number {
  return collator.compare(a, b) || (a < b ? -1 : a > b ? 1 : 0);
}

export function sortFilesNatural(files: File[]): File[] {
  return [...files].sort((a, b) => compareNatural(a.name, b.name));
}

export interface DropPlan {
  /** Ảnh đã xếp theo tên. */
  files: File[];
  /** Ảnh gán vào cảnh đang có: `files[i]` → cảnh `i`. */
  existing: File[];
  /** Chỉ số (từ 0) các cảnh đã có ảnh sẽ bị ghi đè. */
  overwrite: number[];
  /** Ảnh dư cần thêm cảnh mới (sau khi cắt ở 12 cảnh). */
  extra: File[];
  /** Số ảnh vượt quá 12 cảnh, bị bỏ. */
  dropped: number;
}

/**
 * Kế hoạch thả nhiều ảnh (13.B2.1): xếp theo tên tự nhiên, gán từ cảnh 1; cảnh đã có ảnh bị ghi
 * đè; ảnh dư thành cảnh mới (tối đa `MAX_SCENES`), phần vượt thì bỏ.
 */
export function planImageDrop(
  dropped: File[],
  scenes: { image: string }[],
  max = MAX_SCENES,
): DropPlan {
  const files = sortFilesNatural(dropped);
  const count = scenes.length;
  const existing = files.slice(0, count);
  const rest = files.slice(count);
  const room = Math.max(0, max - count);
  const extra = rest.slice(0, room);
  return {
    files,
    existing,
    overwrite: existing.map((_, i) => i).filter((i) => Boolean(scenes[i]?.image)),
    extra,
    dropped: rest.length - extra.length,
  };
}
