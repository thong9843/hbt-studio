import { describe, expect, it } from 'vitest';

// Đợt 5 (IMPLEMENT 13.B7.1): bí danh token/màu cũ và lớp .btn/.input cũ đã bị xoá.
const modules = import.meta.glob(
  [
    '/src/**/*.{ts,tsx,css}',
    '/tailwind.config.ts',
    '!/src/**/*.test.{ts,tsx}',
    '!/src/**/*.d.ts',
    '!/src/i18n/**',
  ],
  { query: '?raw', import: 'default', eager: true },
) as Record<string, string>;

const files = Object.entries(modules);

// Màu Tailwind cũ sinh lớp `bg-surface`, `text-text-muted`, `border-border`, `bg-brand-red`...
// Không bắt `text-muted`, `border`, `border-line`, `rounded-card` (tên gốc / tên v2).
const OLD_CLASS =
  /(?<![\w-])(?:[\w[\]:!-]*:)?(?:[a-z]+-(?:surface-2|surface|text-muted|brand-red|brand-cream|brand-ink)|(?:border|divide|ring|outline|fill|stroke|shadow|from|to|via)-border|rounded-frame)(?![\w-])/;
const OLD_VAR =
  /var\(--(?:surface|surface-2|text-muted|border|brand-red|brand-cream|brand-ink)\)|--(?:surface|surface-2|text-muted|border|brand-red|brand-cream|brand-ink)\s*:/;
const OLD_COMPONENT_CSS = /^\s*(?:textarea)?\.(?:btn|input|card|chip|spinner|label)(?:-[\w-]+)?\b/m;
const OLD_TAILWIND_KEY =
  /^\s*(?:'(?:surface|surface-2|text-muted|border|brand-red|brand-cream|brand-ink)'|(?:surface|border)|frame)\s*:/m;

function classTokens(source: string): string[] {
  const out: string[] = [];
  for (const m of source.matchAll(/className=(?:"([^"]*)"|\{([^}]*)\}|\{`([^`]*)`\})/g)) {
    const text = m[1] ?? m[2] ?? m[3] ?? '';
    for (const t of text.matchAll(/[\w:[\]!./-]+/g)) out.push(t[0]);
  }
  return out;
}

describe('không còn bí danh token / lớp cũ trong frontend', () => {
  it('quét được nguồn', () => {
    expect(files.length).toBeGreaterThan(50);
    expect(files.some(([n]) => n.endsWith('tailwind.config.ts'))).toBe(true);
    expect(files.some(([n]) => n.endsWith('styles/tokens.css'))).toBe(true);
  });

  it.each(files)('%s không dùng tên màu cũ', (_name, src) => {
    expect(src.match(OLD_CLASS)?.[0]).toBeUndefined();
    expect(src.match(OLD_VAR)?.[0]).toBeUndefined();
  });

  it.each(files.filter(([n]) => n.endsWith('.css')))(
    '%s không còn lớp .btn/.input cũ',
    (_n, src) => {
      expect(src.match(OLD_COMPONENT_CSS)?.[0]).toBeUndefined();
    },
  );

  it.each(files.filter(([n]) => n.endsWith('.tsx')))(
    '%s không dùng lớp .btn/.input cũ',
    (_n, src) => {
      const legacy = classTokens(src).filter((t) =>
        /^(btn|btn-[\w-]+|input|chip|chip-[\w-]+|spinner|label|card)$/.test(t),
      );
      expect(legacy).toEqual([]);
    },
  );

  it('tailwind.config.ts không khai tên màu cũ', () => {
    const cfg = files.find(([n]) => n.endsWith('tailwind.config.ts'))![1];
    expect(cfg.match(OLD_TAILWIND_KEY)?.[0]).toBeUndefined();
  });

  it('bắt đúng tên cũ, không bắt nhầm lớp Tailwind gốc / tên v2', () => {
    for (const bad of [
      'bg-surface',
      'hover:bg-surface-2',
      'text-text-muted',
      'border-border',
      'bg-brand-red',
      'rounded-frame',
    ]) {
      expect(OLD_CLASS.test(bad), bad).toBe(true);
    }
    for (const ok of [
      'border',
      'border-line',
      'border-2',
      'text-muted',
      'rounded-card',
      'rounded-full',
      'bg-card',
      'bg-soft',
      'bg-brand',
      'divide-line',
    ]) {
      expect(OLD_CLASS.test(ok), ok).toBe(false);
    }
  });
});
