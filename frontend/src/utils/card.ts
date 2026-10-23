import type { Card, CardLine, CardPreset, LineSize } from '../api/types';

export const CARD_PRESETS: CardPreset[] = ['top', 'upper', 'middle', 'lower'];
export const LINE_SIZES: LineSize[] = ['s', 'm', 'l', 'xl'];
export const MAX_CARD_LINES = 5;
export const CARD_Y_MAX = 1920;
const HEX = /^#[0-9a-fA-F]{6}$/;
const NAMED_COLORS = ['ink', 'primary', 'accent'];

/** Giá trị ô chọn vị trí thẻ: một trong bốn vị trí có sẵn hoặc "custom" khi là số px. */
export function cardPositionKey(y: Card['y']): CardPreset | 'custom' {
  return typeof y === 'number' ? 'custom' : y;
}

/** Ô chọn vị trí → `card.y` gửi cho API. Chọn "custom" mà chưa có số thì bắt đầu ở `fallbackPx`. */
export function cardYFromSelection(
  key: string,
  current: Card['y'],
  fallbackPx = 300,
): CardPreset | number {
  if (key === 'custom') return typeof current === 'number' ? current : fallbackPx;
  if ((CARD_PRESETS as string[]).includes(key)) return key as CardPreset;
  throw new RangeError(`Vị trí thẻ không hợp lệ: ${key}`);
}

/** Số px người dùng nhập → số nguyên trong 0..1920 (rỗng hoặc không phải số → 0). */
export function clampCardY(raw: string | number): number {
  const n = Math.round(Number(raw));
  if (!Number.isFinite(n)) return 0;
  return Math.min(CARD_Y_MAX, Math.max(0, n));
}

export function newCardLine(): CardLine {
  return { text: '', size: 'm', color: 'ink' };
}

/** Màu hợp lệ cho API: tên (ink/primary/accent) hoặc #RRGGBB viết hoa. */
export function normalizeColor(value: string): string {
  if (NAMED_COLORS.includes(value)) return value;
  if (HEX.test(value)) return value.toUpperCase();
  throw new RangeError(`Màu không hợp lệ: ${value}`);
}

/** Dòng thẻ rỗng bị bỏ khi dựng; giữ nguyên thứ tự các dòng còn lại. */
export function nonEmptyLines(card: Card): CardLine[] {
  return card.lines.filter((l) => l.text.trim() !== '');
}
