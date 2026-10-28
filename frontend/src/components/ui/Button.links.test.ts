import { describe, expect, it } from 'vitest';

const modules = import.meta.glob(['/src/**/*.tsx', '!/src/**/*.test.tsx'], {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

describe('<Button> không dùng làm liên kết', () => {
  const files = Object.entries(modules);

  it('quét được nguồn', () => {
    expect(files.length).toBeGreaterThan(30);
  });

  it.each(files)('%s không truyền href / to / as vào <Button>', (_name, src) => {
    const bad = [...src.matchAll(/<Button\b[^>]*?\s(?:href|to|as)=/gs)].map((m) => m[0]);
    expect(bad).toEqual([]);
  });
});
