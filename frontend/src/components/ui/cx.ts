/** Ghép tên lớp CSS, bỏ giá trị rỗng. */
export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(' ');
}
