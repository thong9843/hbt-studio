import type { LineSize } from '../api/types';

/** Giới hạn ký tự mỗi dòng thẻ theo cỡ (K5 của backend; chỉ cảnh báo, không chặn). */
export const LINE_CHAR_LIMIT: Record<LineSize, number> = { xl: 10, l: 15, m: 22, s: 26 };

/** Số ký tự Unicode sau NFC, như Python `len(unicodedata.normalize("NFC", s))`. */
export function countChars(text: string): number {
  return [...text.normalize('NFC')].length;
}

export interface LineCount {
  count: number;
  limit: number;
  over: boolean;
}

/** Bộ đếm một dòng thẻ: `n/giới hạn`, `over` khi vượt (dòng rỗng không bao giờ vượt). */
export function lineCount(size: LineSize, text: string): LineCount {
  const count = countChars(text);
  const limit = LINE_CHAR_LIMIT[size];
  return { count, limit, over: count > limit };
}
