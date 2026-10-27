import { describe, expect, it } from 'vitest';
import tokensCss from '../../styles/tokens.css?raw';
import uiCss from './ui.css?raw';

/** Lấy thân khối `{...}` đầu tiên sau `selector` (có đếm ngoặc lồng nhau). */
function block(css: string, selector: string): string {
  const at = css.indexOf(selector);
  if (at < 0) throw new Error(`Không thấy khối ${selector}`);
  const start = css.indexOf('{', at);
  let depth = 0;
  for (let i = start; i < css.length; i++) {
    if (css[i] === '{') depth++;
    else if (css[i] === '}' && --depth === 0) return css.slice(start + 1, i);
  }
  throw new Error(`Khối ${selector} không đóng`);
}

const tokens = tokensCss.replace(/\/\*[\s\S]*?\*\//g, '');

describe('ui.css performance rules (IMPLEMENT 13.B3.2)', () => {
  const css = uiCss.replace(/\/\*[\s\S]*?\*\//g, '');

  it('has no blur, backdrop-filter, will-change or gradients', () => {
    expect(css).not.toMatch(/backdrop-filter|blur\(|will-change|gradient\(/);
  });

  it('transitions only transform, opacity and colours', () => {
    const lists = [...css.matchAll(/transition\s*:([^;]+);/g)].map((m) => m[1]);
    expect(lists.length).toBeGreaterThan(0);
    for (const l of lists) {
      expect(l).not.toMatch(/\b(all|width|height|top|left|box-shadow|filter)\b/);
    }
  });

  it('keeps durations in 90-200 ms (progress bar 300 ms, spinner 800 ms are the exceptions)', () => {
    const root = block(tokens, ':root {');
    const vars = Object.fromEntries(
      [...root.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)].map((m) => [m[1], m[2].trim()]),
    );
    for (const name of ['--dur-press', '--dur', '--dur-pop', '--dur-slow']) {
      const ms = parseInt(vars[name], 10);
      expect(ms, name).toBeGreaterThanOrEqual(90);
      expect(ms, name).toBeLessThanOrEqual(200);
    }
    const literal = [...css.matchAll(/(\d+)ms/g)].map((m) => Number(m[1]));
    for (const ms of literal) expect([120, 300, 800]).toContain(ms);
  });

  it('only the spinner repeats forever', () => {
    const forever = [...css.matchAll(/([^{}]+)\{[^{}]*infinite[^{}]*\}/g)].map((m) => m[1].trim());
    expect(forever).toEqual(['.ui-spinner']);
  });

  it('turns transforms and entrance animations off for prefers-reduced-motion', () => {
    const rm = block(css, '@media (prefers-reduced-motion: reduce)');
    expect(rm).toContain('transform: none');
    expect(rm).toContain('animation: none');
  });
});
