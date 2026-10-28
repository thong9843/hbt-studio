import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import indexHtml from '../index.html?raw';
import { THEME_KEY } from './utils/theme';

/** Script chặn (không `type="module"`) đầu tiên trong <head>. */
function bootScript(): { code: string; at: number } {
  const m = /<script>([\s\S]*?)<\/script>/.exec(indexHtml);
  if (!m) throw new Error('index.html thiếu script áp chế độ');
  return { code: m[1], at: m.index };
}

const run = () => new Function(bootScript().code)();

beforeEach(() => document.documentElement.removeAttribute('data-theme'));
afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
  document.documentElement.removeAttribute('data-theme');
});

describe('index.html áp chế độ trước lần vẽ đầu', () => {
  it('runs before the app bundle and before #root, as a blocking inline script', () => {
    const { at } = bootScript();
    expect(at).toBeLessThan(indexHtml.indexOf('id="root"'));
    expect(at).toBeLessThan(indexHtml.indexOf('src="/src/main.tsx"'));
    expect(indexHtml.slice(at, at + 8)).toBe('<script>'); // không module / defer / async
  });

  it('uses the same storage key as the app', () => {
    expect(bootScript().code).toContain(`'${THEME_KEY}'`);
  });

  it.each(['dark', 'light'])('applies a stored %s choice to <html>', (mode) => {
    localStorage.setItem(THEME_KEY, mode);
    run();
    expect(document.documentElement).toHaveAttribute('data-theme', mode);
  });

  it('leaves <html> alone with no choice or a junk value (follows the system)', () => {
    run();
    expect(document.documentElement).not.toHaveAttribute('data-theme');
    localStorage.setItem(THEME_KEY, 'purple');
    run();
    expect(document.documentElement).not.toHaveAttribute('data-theme');
  });

  it('survives localStorage throwing', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(run).not.toThrow();
    expect(document.documentElement).not.toHaveAttribute('data-theme');
  });
});
