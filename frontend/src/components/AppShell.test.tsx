import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ProjectsPage } from '../pages/ProjectsPage';
import { useRenderJob } from '../hooks/renderJob';
import { FakeEventSource, stubFetch } from '../test/fakes';
import { renderWithProviders } from '../test/render';
import { AppShell } from './AppShell';
import { RenderCard } from './SideNav';

afterEach(() => vi.unstubAllGlobals());

const health = {
  ok: true,
  ffmpeg: true,
  whisper: false,
  gpu: false,
  vieneu: true,
  vieneu_note: null,
  missing: [],
};
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
        <Route path="/" element={<Where />} />
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/p/:slug/*" element={<Where />} />
        <Route path="/postv/*" element={<Where />} />
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
    expect(labels).toEqual(['Trang chủ', 'Dự án', 'PostV', 'Cài đặt']);
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

  it('marks Home as current at "/" and Projects at "/projects"', () => {
    stubFetch(routes());
    const first = shell('/');
    expect(screen.getByRole('link', { name: 'Trang chủ' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'Trang chủ' })).toHaveAttribute('href', '/');
    expect(screen.getByRole('link', { name: 'Dự án' })).not.toHaveAttribute('aria-current');
    first.unmount();
    shell('/projects');
    expect(screen.getByRole('link', { name: 'Dự án' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'Dự án' })).toHaveAttribute('href', '/projects');
    expect(screen.getByRole('link', { name: 'Trang chủ' })).not.toHaveAttribute('aria-current');
  });

  it('has its own PostV item: /postv is current on the PostV screens, not on Projects', async () => {
    stubFetch(routes());
    shell('/postv/bai/pick');
    expect(await screen.findByRole('link', { name: 'PostV' })).toHaveAttribute('href', '/postv');
    expect(screen.getByRole('link', { name: 'PostV' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'Dự án' })).not.toHaveAttribute('aria-current');
    expect(screen.queryByRole('group', { name: 'Dự án đang mở' })).toBeNull(); // bước nằm ở thanh ngang
  });

  it('opens the new-video dialog from the red button, on any screen', async () => {
    stubFetch(routes());
    shell('/p/muoi');
    await userEvent.click(screen.getByRole('button', { name: 'Tạo video' }));
    expect(await screen.findByRole('dialog', { name: 'Tạo video mới' })).toBeInTheDocument();
    expect(screen.getByTestId('where')).toHaveTextContent('/p/muoi');
  });

  it('ignores the old /?new=1 query: no dialog opens', async () => {
    stubFetch(routes());
    shell('/?new=1');
    await screen.findByRole('link', { name: 'Dự án' });
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('is reachable by keyboard in reading order', async () => {
    stubFetch(routes());
    shell();
    const order = ['HBT Studio', 'Tạo video', 'Trang chủ', 'Dự án', 'PostV', 'Cài đặt'];
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

  it('follows the global job and survives a change of screen', async () => {
    FakeEventSource.instances = [];
    vi.stubGlobal('EventSource', FakeEventSource);
    stubFetch({ ...routes(), 'POST /api/projects/muoi/render': { job_id: 'j1' } });
    function Starter() {
      const rj = useRenderJob();
      return (
        <button type="button" onClick={() => void rj.start('muoi', { preview: true })}>
          go
        </button>
      );
    }
    renderWithProviders(
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<Starter />} />
          <Route path="/projects" element={<Where />} />
        </Route>
      </Routes>,
      '/',
    );
    expect(screen.queryByRole('status', { name: 'Đang dựng' })).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'go' }));
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    act(() =>
      FakeEventSource.instances[0].emit('progress', { progress: 55, step: 'Mã hoá', message: '' }),
    );
    await userEvent.click(screen.getByRole('link', { name: 'Dự án' }));
    const card = screen.getByRole('status', { name: 'Đang dựng' });
    expect(card).toHaveTextContent('55%');
    expect(card).toHaveTextContent('Mã hoá');
    expect(FakeEventSource.instances).toHaveLength(1);
  });

  it('shows "Đang ước tính…" at 0%, then "Còn ≈ …" and a Huỷ button that cancels', async () => {
    FakeEventSource.instances = [];
    vi.stubGlobal('EventSource', FakeEventSource);
    const mock = stubFetch({
      ...routes(),
      'POST /api/projects/muoi/render': { job_id: 'j1' },
      'POST /api/jobs/j1/cancel': { id: 'j1', status: 'cancelled' },
    });
    function Starter() {
      const rj = useRenderJob();
      return (
        <button type="button" onClick={() => void rj.start('muoi', { preview: true }, 100)}>
          go
        </button>
      );
    }
    renderWithProviders(
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<Starter />} />
        </Route>
      </Routes>,
      '/',
    );
    await userEvent.click(screen.getByRole('button', { name: 'go' }));
    const card = await screen.findByRole('status', { name: 'Đang dựng' });
    expect(card).toHaveTextContent('Đang ước tính…');
    act(() =>
      FakeEventSource.instances[0].emit('progress', { progress: 25, step: 'Ghép', message: '' }),
    );
    expect(card).toHaveTextContent('Còn ≈ 1 phút 15 giây');
    await userEvent.click(within(card).getByRole('button', { name: 'Huỷ' }));
    expect(mock).toHaveBeenCalledWith(
      '/api/jobs/j1/cancel',
      expect.objectContaining({ method: 'POST' }),
    );
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
    expect(list).toHaveTextContent('VieNeu: có'); // K-40
  });

  it('shows VieNeu as missing when the backend says so', async () => {
    stubFetch({
      ...routes(),
      'GET /api/health': { ...health, vieneu: false, vieneu_note: 'Chưa cài VieNeu' },
    });
    shell('/settings');
    const list = await screen.findByRole('list', { name: 'Trạng thái môi trường' });
    await waitFor(() => expect(list).toHaveTextContent('VieNeu: thiếu'));
  });
});
