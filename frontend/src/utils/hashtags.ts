/** Chuỗi người dùng gõ → danh sách hashtag lưu trong project: bỏ `#` đầu, cắt khoảng trắng, NFC. */
export function parseHashtags(raw: string): string[] {
  return raw
    .split(/[\s,]+/)
    .map((t) => t.normalize('NFC').replace(/^#+/, '').trim())
    .filter((t) => t !== '');
}
