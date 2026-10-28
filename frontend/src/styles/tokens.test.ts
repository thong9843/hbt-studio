import { describe, expect, it } from 'vitest';
import tokensCss from './tokens.css?raw';

/** Lấy thân khối `{...}` đầu tiên sau `selector` (có đếm ngoặc lồng nhau). */
function block(css: string, selector: string, from = 0): string {
  const at = css.indexOf(selector, from);
  if (at < 0) throw new Error(`Không thấy khối ${selector}`);
  const start = css.indexOf('{', at);
  let depth = 0;
  for (let i = start; i < css.length; i++) {
    if (css[i] === '{') depth++;
    else if (css[i] === '}' && --depth === 0) return css.slice(start + 1, i);
  }
  throw new Error(`Khối ${selector} không đóng`);
}

function decls(body: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const m of body.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) out[m[1]] = m[2].trim();
  return out;
}

const stripped = tokensCss.replace(/\/\*[\s\S]*?\*\//g, '');
const light = decls(block(stripped, ':root {'));
const darkMedia = decls(block(block(stripped, '@media (prefers-color-scheme: dark)'), ':root'));
const darkAttr = decls(block(stripped, ":root[data-theme='dark']"));

/** Giải `var(--x)` về giá trị cuối; chế độ tối phủ lên chế độ sáng. */
function resolver(theme: 'light' | 'dark') {
  const all = { ...light, ...(theme === 'dark' ? darkAttr : {}) };
  // Khối :root thứ hai (bí danh) cũng nằm trong `light`? Không: block() chỉ lấy khối đầu.
  Object.assign(all, decls(stripped.slice(stripped.lastIndexOf(':root {'))));
  const get = (name: string, depth = 0): string => {
    const v = all[name];
    if (v === undefined) throw new Error(`Thiếu token ${name}`);
    const ref = /^var\((--[\w-]+)\)$/.exec(v);
    if (ref && depth < 8) return get(ref[1], depth + 1);
    return v;
  };
  return get;
}

function channel(c: number): number {
  const s = c / 255;
  return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}
function luminance(hex: string): number {
  const m = /^#([0-9a-f]{6})$/i.exec(hex);
  if (!m) throw new Error(`Không phải màu #rrggbb: ${hex}`);
  const n = parseInt(m[1], 16);
  return 0.2126 * channel(n >> 16) + 0.7152 * channel((n >> 8) & 255) + 0.0722 * channel(n & 255);
}
export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

describe('tokens.css v2', () => {
  it('declares every token of DESIGN-HBT.md section 2 in light mode', () => {
    for (const name of [
      '--bg',
      '--card',
      '--soft',
      '--soft-2',
      '--line',
      '--text',
      '--text-2',
      '--muted',
      '--primary',
      '--on-primary',
      '--accent',
      '--on-accent',
      '--brand',
      '--on-brand',
      '--tint-red',
      '--on-tint-red',
      '--tint-yel',
      '--on-tint-yel',
      '--ok',
      '--ok-soft',
      '--on-ok-soft',
      '--danger',
      '--on-danger',
    ]) {
      expect(light[name], name).toBeDefined();
    }
  });

  it('uses the exact light and dark values of DESIGN-HBT.md', () => {
    const l = resolver('light');
    const d = resolver('dark');
    expect([l('--bg'), l('--card'), l('--soft'), l('--line'), l('--text')]).toEqual([
      '#f5f5f7',
      '#ffffff',
      '#f0f0f3',
      '#ececf0',
      '#16120f',
    ]);
    expect([d('--bg'), d('--card'), d('--soft'), d('--line'), d('--text')]).toEqual([
      '#0f0f12',
      '#18181c',
      '#26262c',
      '#26262c',
      '#f4f4f6',
    ]);
    expect([l('--accent'), l('--brand'), l('--danger')]).toEqual(['#f4b630', '#b22228', '#b3261e']);
    expect([d('--accent'), d('--brand'), d('--danger')]).toEqual(['#f4b630', '#b22228', '#ff6b6b']);
  });

  it('has radii and shadows from section 4', () => {
    expect(light['--radius-card']).toBe('24px');
    expect(light['--radius-dialog']).toBe('28px');
    expect(light['--radius-input']).toBe('14px');
    expect(light['--radius-pill']).toBe('999px');
    expect(darkAttr['--shadow-card']).toBe('none');
    expect(darkAttr['--card-border']).toBe('var(--line)');
  });

  it('keeps the system-dark block and the data-theme=dark block identical', () => {
    expect(darkMedia).toEqual(darkAttr);
  });

  it('only overrides tokens that exist in light mode', () => {
    for (const name of Object.keys(darkAttr)) expect(light[name], name).toBeDefined();
  });

  it('keeps old token names as aliases pointing at v2', () => {
    const alias = decls(stripped.slice(stripped.lastIndexOf(':root {')));
    expect(alias['--surface']).toBe('var(--card)');
    expect(alias['--text-muted']).toBe('var(--muted)');
    expect(alias['--border']).toBe('var(--line)');
    expect(alias['--brand-red']).toBe('var(--brand)');
  });
});

// Mọi cặp chữ/nền >= 4,5:1 ở cả hai chế độ (DESIGN-HBT mục 8).
const PAIRS: [string, string][] = [
  ['--text', '--bg'],
  ['--text', '--card'],
  ['--text', '--nav'],
  ['--text', '--soft'],
  ['--text', '--soft-2'],
  ['--text-2', '--bg'],
  ['--text-2', '--card'],
  ['--text-2', '--nav'],
  ['--text-2', '--soft'],
  ['--muted', '--bg'],
  ['--muted', '--card'],
  ['--muted', '--nav'],
  ['--muted', '--soft'],
  ['--muted', '--soft-2'],
  ['--on-primary', '--primary'],
  ['--on-hero', '--hero'],
  ['--on-accent', '--accent'],
  ['--on-brand', '--brand'],
  ['--on-tint-red', '--tint-red'],
  ['--on-tint-yel', '--tint-yel'],
  ['--on-ok-soft', '--ok-soft'],
  ['--on-danger', '--danger'],
  ['--danger', '--bg'],
  ['--danger', '--card'],
  ['--danger', '--danger-soft'],
  ['--text', '--tint-yel'],
];

describe.each(['light', 'dark'] as const)('contrast (%s)', (theme) => {
  const get = resolver(theme);
  it.each(PAIRS)('%s on %s is at least 4.5:1', (fg, bg) => {
    const ratio = contrast(get(fg), get(bg));
    expect(
      ratio,
      `${fg} ${get(fg)} / ${bg} ${get(bg)} = ${ratio.toFixed(2)}`,
    ).toBeGreaterThanOrEqual(4.5);
  });
});

describe('hero card tokens', () => {
  it('stay dark in both modes (never follow --primary)', () => {
    for (const dark of [darkMedia, darkAttr]) {
      expect(dark['--hero']).toBeUndefined();
      expect(dark['--on-hero']).toBeUndefined();
    }
    expect(resolver('dark')('--hero')).toBe(resolver('light')('--hero'));
    expect(luminance(resolver('dark')('--hero'))).toBeLessThan(0.05);
  });
});

describe('contrast helper', () => {
  it('gives 21:1 for black on white and 1:1 for equal colours', () => {
    expect(contrast('#000000', '#ffffff')).toBeCloseTo(21, 5);
    expect(contrast('#777777', '#777777')).toBeCloseTo(1, 5);
  });
});
