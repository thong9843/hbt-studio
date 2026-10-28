import { describe, expect, it } from 'vitest';

const modules = import.meta.glob(['./*.tsx', '!./*.test.tsx', '!./scriptTestKit.tsx'], {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

/** Chuỗi trong thuộc tính className (kể cả `className={cx('a', 'b')}`). */
function classTokens(source: string): string[] {
  const out: string[] = [];
  for (const m of source.matchAll(/className=(?:"([^"]*)"|\{([^}]*)\}|\{`([^`]*)`\})/g)) {
    const text = m[1] ?? m[2] ?? m[3] ?? '';
    for (const t of text.matchAll(/[\w:[\]!./-]+/g)) out.push(t[0]);
  }
  return out;
}

describe('Hộp Dán JSON và Bản sao lưu dùng components/ui/*, không dùng lớp cũ', () => {
  const files = Object.entries(modules);

  it('loaded the component sources', () => {
    expect(files.length).toBeGreaterThanOrEqual(4);
  });

  it.each(files)(
    '%s has no legacy .btn / .input / .chip / .spinner / .label / .card',
    (name, src) => {
      const legacy = classTokens(src).filter((t) =>
        /^(btn|btn-[\w-]+|input|chip|chip-[\w-]+|spinner|label|card)$/.test(t),
      );
      expect(legacy, name).toEqual([]);
    },
  );

  it.each(files)('%s has no hard-coded Vietnamese UI text outside i18n', (name, src) => {
    // Chữ hiển thị nằm ở vi.ts; trong mã chỉ cho phép chuỗi có dấu ở thông báo lỗi nội bộ.
    const jsxText = [...src.matchAll(/>([^<>{}\n]*[À-ỹ][^<>{}\n]*)</g)].map((m) => m[1].trim());
    expect(jsxText, name).toEqual([]);
  });
});
