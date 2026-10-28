import { describe, expect, it } from 'vitest';

const modules = import.meta.glob(['./AudioTab.tsx', '../components/audio/*.tsx'], {
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

describe('Âm thanh dùng components/ui/*, không dùng lớp cũ', () => {
  const files = Object.entries(modules);

  it('loaded the screen sources', () => {
    expect(files.length).toBeGreaterThanOrEqual(7);
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

  it.each(files)('%s uses no raw <button>/<input> (components/ui instead)', (name, src) => {
    const raw = src.match(/<(button|input)\b/g)?.filter(() => !/AudioDrop\.tsx$/.test(name));
    expect(raw ?? [], name).toEqual([]);
  });
});
