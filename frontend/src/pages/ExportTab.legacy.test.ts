import { describe, expect, it } from 'vitest';

const modules = import.meta.glob(['./ExportTab.tsx', '../components/export/*.tsx'], {
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

describe('Xuất video dùng components/ui/*, không dùng lớp cũ', () => {
  const files = Object.entries(modules);

  it('loaded the screen sources', () => {
    expect(files.length).toBeGreaterThanOrEqual(6);
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

  it.each(files)('%s uses no raw <input> and no ProgressBar cũ', (name, src) => {
    expect(src.match(/<input\b/g) ?? [], name).toEqual([]);
    expect(src, name).not.toMatch(/components\/ProgressBar|from '\.\/ProgressBar'/);
  });

  it.each(files.filter(([n]) => !/HistoryGrid\.tsx$/.test(n)))(
    '%s uses <Button>, not a raw <button> (only the history card is a button)',
    (name, src) => {
      expect(src.match(/<button\b/g) ?? [], name).toEqual([]);
    },
  );
});
