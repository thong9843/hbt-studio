import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ProjectsPage } from '../pages/ProjectsPage';
import { stubFetch } from '../test/fakes';
import { renderWithProviders } from '../test/render';
import { AppShell } from './AppShell';
import { RenderCard } from './SideNav';

afterEach(() => vi.unstubAllGlobals());

const health = { ok: true, ffmpeg: true, whisper: false, gpu: false, missing: [] };
const summary = (slug: string, title: string) => ({
  slug,
  title,
  updated_at: '2026-10-22T10:00:00',
  thumb: null,
  last_render: null,
  last_final: null,
  cover: null,
  error: null,
});
const routes = () => ({
  'GET /api/health': health,
  'GET /api/projects': [summary('muoi', 'Vì sao muỗi đốt bạn')],
});

function Where() {
  const l = useLocation();
  return <p data-testid="where">{l.pathname + l.search}</p>;
}

function shell(route = '/', render?: { percent: number; step: string } | null) {
  return renderWithProviders(
    <Routes>
      <Route element={<AppShell render={render} />}>
        <Route path="/" element={<ProjectsPage />} />
        <Route path="/p/:slug/*" element={<Where />} />
        <Route path="/settings" element={<Where />} />
      </Route>
    </Routes>,
    route,
  );
}

/** Mô phỏng cửa sổ hẹp: `(min-width: 1280px)` không khớp. */
function narrowScreen() {
  const original = window.matchMedia;
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent: () => false,
  })) as typeof window.matchMedia;
  return () => {
    window.matchMedia = original;
  };
}

describe('AppShell, wide (>= 1280 px)', () => {
  it('shows the logo, the red create button and the main items in order', async () => {
    stubFetch(routes());
    shell();
    const nav = screen.getByRole('navigation', { name: 'Điều hướng chính' });
    expect(screen.getByText('HBT Studio')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Tạo video' })).toHaveClass('ui-btn-brand');
    const labels = within(nav)
      .getAllByRole('link')
      .map((a) => a.textContent);
    expect(labels).toEqual(['Trang chủ', 'Dự án', 'Cài đặt']);
    expect(await screen.findByRole('list', { name: 'Trạng thái môi trường' })).toBeInTheDocument();
  });

  it('is 232 px wide and fixed in place', () => {
    stubFetch(routes());
    shell();
    const side = screen.getByRole('complementary');
    expect(side).toHaveClass('w-[232px]', 'sticky', 'h-screen');
  });

  it('hides the open-project block outside a project', () => {
    stubFetch(routes());
    shell('/');
    expect(screen.queryByRole('group', { name: 'Dự án đang mở' })).toBeNull();
    expect(screen.queryByRole('link', { name: 'Soạn video' })).toBeNull();
  });

  it('shows the open project with its name and three links inside /p/:slug', async () => {
    stubFetch(routes());
    shell('/p/muoi/audio');
    const group = screen.getByRole('group', { name: 'Dự án đang mở' });
    expect(await within(group).findByText('Vì sao muỗi đốt bạn')).toBeInTheDocument();
    const links = within(group).getAllByRole('link');
    expect(links.map((a) => a.textContent)).toEqual(['Soạn video', 'Âm thanh', 'Xuất video']);
    expect(links.map((a) => a.getAttribute('href'))).toEqual([
      '/p/muoi',
      '/p/muoi/audio',
      '/p/muoi/export',
    ]);
    // Chỉ mục đang ở được đánh dấu.
    expect(within(group).getByRole('link', { name: 'Âm thanh' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(within(group).getByRole('link', { name: 'Soạn video' })).not.toHaveAttribute(
      'aria-current',
    );
  });

  it('falls back to the slug until the project list arrives', () => {
    stubFetch(routes());
    shell('/p/muoi');
    expect(
      within(screen.getByRole('group', { name: 'Dự án đang mở' })).getByText('muoi'),
    ).toBeInTheDocument();
  });

  it('marks Projects as current at "/" and leaves Home unmarked until the Home screen exists', () => {
    stubFetch(routes());
    shell('/');
    expect(screen.getByRole('link', { name: 'Dự án' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'Trang chủ' })).not.toHaveAttribute('aria-current');
    expect(screen.getByRole('link', { name: 'Trang chủ' })).toHaveAttribute('href', '/');
  });

  it('opens the old create dialog from the red button (via /?new=1)', async () => {
    stubFetch(routes());
    shell('/p/muoi');
    await userEvent.click(screen.getByRole('button', { name: 'Tạo video' }));
    expect(await screen.findByRole('dialog', { name: 'Tạo video mới' })).toBeInTheDocument();
  });

  it('opens the create dialog and clears the query so a reload does not reopen it', async () => {
    stubFetch(routes());
    shell('/?new=1');
    expect(await screen.findByRole('dialog', { name: 'Tạo video mới' })).toBeInTheDocument();
  });

  it('is reachable by keyboard in reading order', async () => {
    stubFetch(routes());
    shell();
    const order = ['HBT Studio', 'Tạo video', 'Trang chủ', 'Dự án', 'Cài đặt'];
    for (const name of order) {
      await userEvent.tab();
      expect(document.activeElement).toHaveAccessibleName(name);
    }
  });
});

describe('AppShell, narrow (< 1280 px)', () => {
  it('collapses to 72 px with icons only, still named for screen readers', () => {
    const restore = narrowScreen();
    try {
      stubFetch(routes());
      shell('/p/muoi');
      expect(screen.getByRole('complementary')).toHaveClass('w-[72px]');
      expect(screen.queryByText('HBT Studio')).toBeNull();
      // Chữ còn trong DOM dưới dạng sr-only, và có tooltip.
      const home = screen.getByRole('link', { name: 'Dự án' });
      expect(home).toHaveAttribute('title', 'Dự án');
      expect(within(home).getByText('Dự án')).toHaveClass('sr-only');
      expect(screen.getByRole('button', { name: 'Tạo video' })).toBeInTheDocument();
      expect(screen.getByRole('link', { name: 'Xuất video' })).toHaveAttribute(
        'title',
        'Xuất video',
      );
      // Tên dự án không hiện ở chế độ thu.
      expect(screen.queryByText('muoi')).toBeNull();
    } finally {
      restore();
    }
  });
});

describe('render progress card', () => {
  it('shows percent, step and a progress bar', () => {
    renderWithProviders(<RenderCard mini={false} render={{ percent: 42.4, step: 'Ghép cảnh' }} />);
    const card = screen.getByRole('status', { name: 'Đang dựng' });
    expect(card).toHaveTextContent('42%');
    expect(card).toHaveTextContent('Ghép cảnh');
    expect(screen.getByRole('progressbar', { name: 'Tiến độ dựng' })).toHaveAttribute(
      'aria-valuenow',
      '42',
    );
  });

  it('is shown by AppShell only when the prop is given', () => {
    stubFetch(routes());
    const first = shell('/');
    expect(screen.queryByRole('status', { name: 'Đang dựng' })).toBeNull();
    first.unmount();
    shell('/', { percent: 10, step: 'Căn chữ' });
    expect(screen.getByRole('status', { name: 'Đang dựng' })).toHaveTextContent('Căn chữ');
  });

  it('collapses to a bare bar with a tooltip in mini mode', () => {
    renderWithProviders(<RenderCard mini render={{ percent: 70, step: 'Mã hoá' }} />);
    expect(screen.queryByRole('status')).toBeNull();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '70');
  });
});

describe('environment dots', () => {
  const healthCalls = (mock: ReturnType<typeof stubFetch>) =>
    mock.mock.calls.filter(([url]) => String(url).endsWith('/api/health')).length;

  it('does not poll while idle', async () => {
    const mock = stubFetch(routes());
    shell('/settings');
    await screen.findByRole('list', { name: 'Trạng thái môi trường' });
    await waitFor(() => expect(healthCalls(mock)).toBe(1));
    vi.useFakeTimers();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5 * 60_000);
    });
    expect(healthCalls(mock)).toBe(1);
  });

  it('refetches when the tab regains focus', async () => {
    const mock = stubFetch(routes());
    shell('/settings');
    await waitFor(() => expect(healthCalls(mock)).toBe(1));
    act(() => {
      window.dispatchEvent(new Event('visibilitychange'));
    });
    await waitFor(() => expect(healthCalls(mock)).toBe(2));
  });

  it('names each state in text, not only by colour', async () => {
    stubFetch(routes());
    shell('/settings');
    const list = await screen.findByRole('list', { name: 'Trạng thái môi trường' });
    await waitFor(() => expect(list).toHaveTextContent('FFmpeg: có'));
    expect(list).toHaveTextContent('Whisper: thiếu');
    expect(list).toHaveTextContent('GPU: thiếu');
  });
});
