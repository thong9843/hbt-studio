import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { stubFetch } from '../test/fakes';
import { renderWithProviders } from '../test/render';
import { THEME_KEY } from '../utils/theme';
import { AppShell } from './AppShell';

const health = { ok: true, ffmpeg: true, whisper: false, gpu: false, missing: [] };

function shell() {
  stubFetch({ 'GET /api/health': health, 'GET /api/projects': [] });
  return renderWithProviders(
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<p>home</p>} />
      </Route>
    </Routes>,
  );
}

/** Hệ thống đang ở chế độ `dark` hay không; `(min-width…)` vẫn khớp như setup. */
function systemPrefers(dark: boolean) {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: /prefers-color-scheme: dark/.test(query) ? dark : /min-width/.test(query),
    media: query,
    addEventListener() {},
    removeEventListener() {},
  }));
}

beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute('data-theme');
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  document.documentElement.removeAttribute('data-theme');
});

describe('nút Sáng ↔ Tối ở thanh trái', () => {
  it('first visit follows the system and writes nothing', () => {
    systemPrefers(true);
    shell();
    const btn = screen.getByRole('button', { name: 'Đổi sang chế độ sáng' });
    expect(btn).toHaveAttribute('aria-pressed', 'true');
    expect(btn).toHaveTextContent('Tối');
    expect(localStorage.getItem(THEME_KEY)).toBeNull();
    expect(document.documentElement).not.toHaveAttribute('data-theme');
  });

  it('shows the current mode, and a click switches, applies and remembers it', async () => {
    systemPrefers(false);
    shell();
    const btn = screen.getByRole('button', { name: 'Đổi sang chế độ tối' });
    expect(btn).toHaveAttribute('aria-pressed', 'false');
    expect(btn).toHaveTextContent('Sáng');
    await userEvent.click(btn);
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark');
    expect(localStorage.getItem(THEME_KEY)).toBe('dark');
    expect(screen.getByRole('button', { name: 'Đổi sang chế độ sáng' })).toHaveTextContent('Tối');
  });

  it('a stored choice wins over the system', () => {
    systemPrefers(true);
    localStorage.setItem(THEME_KEY, 'light');
    shell();
    expect(screen.getByRole('button', { name: 'Đổi sang chế độ tối' })).toHaveTextContent('Sáng');
  });

  it('still switches when localStorage throws', async () => {
    systemPrefers(false);
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    shell();
    await userEvent.click(screen.getByRole('button', { name: 'Đổi sang chế độ tối' }));
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark');
  });

  it('stays usable when the side bar shrinks to 72 px (icon only, still named)', () => {
    systemPrefers(false);
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: false,
      media: query,
      addEventListener() {},
      removeEventListener() {},
    }));
    shell();
    const btn = screen.getByRole('button', { name: 'Đổi sang chế độ tối' });
    expect(btn).toHaveAttribute('title', 'Đổi sang chế độ tối');
    expect(btn).not.toHaveTextContent('Sáng');
  });
});
