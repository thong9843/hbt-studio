import { describe, expect, it } from 'vitest';

const modules = import.meta.glob(
  [
    './ScenesTab.tsx',
    './ComposePage.tsx',
    '../components/compose/*.tsx',
    '../components/ThumbnailEditor.tsx',
    '../components/SaveIndicator.tsx',
    '../hooks/useImageDrop.tsx',
  ],
  { query: '?raw', import: 'default', eager: true },
) as Record<string, string>;

/** Chuỗi trong thuộc tính className (kể cả `className={cx('a', 'b')}`). */
function classTokens(source: string): string[] {
  const out: string[] = [];
  for (const m of source.matchAll(/className=(?:"([^"]*)"|\{([^}]*)\})/g)) {
    const text = m[1] ?? m[2] ?? '';
    for (const t of text.matchAll(/[\w:[\]!./-]+/g)) out.push(t[0]);
  }
  return out;
}

describe('Soạn video dùng components/ui/*, không dùng lớp cũ', () => {
  const files = Object.entries(modules).filter(([name]) => !name.endsWith('.test.tsx'));

  it('loaded the screen sources', () => {
    expect(files.length).toBeGreaterThan(8);
  });

  it.each(files)(
    '%s has no legacy .btn / .input / .chip / .spinner / .label classes',
    (name, src) => {
      const legacy = classTokens(src).filter((t) =>
        /^(btn|btn-[\w-]+|input|chip|chip-[\w-]+|spinner|label)$/.test(t),
      );
      expect(legacy, name).toEqual([]);
    },
  );
});
