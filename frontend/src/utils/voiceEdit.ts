export type VoiceMark = 'break' | 'number';

export interface VoiceEdit {
  text: string;
  /** Vị trí con trỏ sau khi chèn. */
  caret: number;
}

/**
 * Chèn cú pháp lời đọc tại vùng chọn [start, end]:
 * - `break`: thêm `|` (thay phần đang chọn không đổi, chèn tại `end`);
 * - `number`: thêm `{}` ngay sau phần đang chọn (chữ hiện), con trỏ vào giữa `{}` để gõ chữ đọc.
 */
export function insertVoiceMark(
  text: string,
  start: number,
  end: number,
  mark: VoiceMark,
): VoiceEdit {
  const s = Math.max(0, Math.min(start, text.length));
  const e = Math.max(s, Math.min(end, text.length));
  if (mark === 'break') {
    return { text: `${text.slice(0, e)}|${text.slice(e)}`, caret: e + 1 };
  }
  return { text: `${text.slice(0, e)}{}${text.slice(e)}`, caret: e + 1 };
}
