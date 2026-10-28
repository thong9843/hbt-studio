import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { NewProjectProvider } from '../components/NewProjectDialog';
import { ToastProvider } from '../components/Toast';
import { stubFetch } from '../test/fakes';
import { project } from '../test/project';
import { renderWithProviders } from '../test/render';
import { HomePage } from './HomePage';

afterEach(() => vi.unstubAllGlobals());

const render = (over: Record<string, unknown> = {}) => ({
  job_id: 'a',
  preview: false,
  fps: 50,
  duration: 83,
  render_seconds: 143.4,
  created_at: '2026-10-22T10:00:00Z',
  video: '/api/files/projects/muoi/renders/a/video.mp4',
  ...over,
});
const summary = (slug: string, title: string, over: Record<string, unknown> = {}) => ({
  slug,
  title,
  updated_at: '2026-10-22T10:00:00Z',
  thumb: null,
  cover: null,
  last_render: null,
  last_final: null,
  error: null,
  ...over,
});
const json = (body: unknown) =>
  new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } });

function page() {
  return renderWithProviders(
    <ToastProvider>
      <NewProjectProvider>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/projects" element={<p>trang dự án</p>} />
          <Route path="/p/:slug" element={<p>trang soạn</p>} />
        </Routes>
      </NewProjectProvider>
    </ToastProvider>,
  );
}

const brief = project({
  slug: 'muoi',
  title: 'Muỗi',
  series: 'Vì sao vậy ta?',
  voice: 'voice.wav',
  music: { file: null, start: null, credit: '' },
});

describe('HomePage', () => {
  it('greets with the title and shows skeletons while loading', async () => {
    stubFetch({ 'GET /api/projects': [summary('muoi', 'Muỗi')], 'GET /api/projects/muoi': brief });
    page();
    expect(screen.getByRole('heading', { level: 1, name: 'Hôm nay làm video gì?' })).toBeVisible();
    expect(screen.getAllByRole('status', { name: 'Đang tải' }).length).toBeGreaterThan(0);
    await screen.findByRole('region', { name: 'Tiếp tục làm' });
  });

  it('"Tiếp tục làm" is the most recently edited project, with status, series and readiness dots', async () => {
    const get = vi.fn(() => json(brief));
    stubFetch({
      'GET /api/projects': [
        summary('muoi', 'Muỗi', { last_final: render(), last_render: render() }),
        summary('cu', 'Dự án cũ'),
      ],
      'GET /api/projects/muoi': get,
    });
    page();
    const card = await screen.findByRole('region', { name: 'Tiếp tục làm' });
    expect(within(card).getByRole('heading', { name: 'Muỗi' })).toBeVisible();
    expect(within(card).getByText('Đã xuất · 50 fps')).toBeVisible();
    expect(await within(card).findByText('Vì sao vậy ta?')).toBeVisible();
    const dots = within(card).getByRole('list', { name: 'Nguyên liệu đã có' });
    expect(within(dots).getByText('Ảnh 2/3')).toBeVisible();
    // Trạng thái không chỉ bằng màu: mỗi chấm có chữ cho trình đọc.
    expect(within(dots).getByText('Giọng').parentElement).toHaveTextContent('(đã có)');
    expect(within(dots).getByText('Nhạc').parentElement).toHaveTextContent('(chưa có)');
    expect(within(dots).getByText('Ảnh bìa').parentElement).toHaveTextContent('(chưa có)');
    expect(within(card).getByRole('link', { name: 'Mở dự án' })).toHaveAttribute('href', '/p/muoi');
    expect(within(card).getByRole('link', { name: /Xem video/ })).toHaveAttribute(
      'href',
      '/api/files/projects/muoi/renders/a/video.mp4',
    );
    // Chỉ một lần GET project, không poll.
    expect(get).toHaveBeenCalledTimes(1);
  });

  it('hides "Xem video" when the project has no video file', async () => {
    stubFetch({
      'GET /api/projects': [summary('muoi', 'Muỗi')],
      'GET /api/projects/muoi': brief,
    });
    page();
    const card = await screen.findByRole('region', { name: 'Tiếp tục làm' });
    expect(within(card).queryByRole('link', { name: /Xem video/ })).toBeNull();
    expect(within(card).getByText('Chưa dựng')).toBeVisible();
  });

  it('"Lần xuất gần nhất" uses the summary only (no /renders request) and shows fps, length, build time', async () => {
    const fetchMock = stubFetch({
      'GET /api/projects': [
        summary('muoi', 'Muỗi', { last_final: render({ fps: 60 }) }),
        summary('cu', 'Dự án cũ', {
          last_final: render({ created_at: '2026-10-01T10:00:00Z', fps: 30 }),
        }),
      ],
      'GET /api/projects/muoi': brief,
    });
    page();
    const card = await screen.findByRole('region', { name: 'Lần xuất gần nhất' });
    expect(within(card).getByRole('heading', { name: 'Muỗi' })).toBeVisible();
    expect(within(card).getByText('60')).toBeVisible();
    expect(within(card).getByText('1:23')).toBeVisible();
    expect(within(card).getByText('2:23')).toBeVisible();
    expect(within(card).getByText(/Bản đẹp/)).toBeVisible();
    expect(JSON.stringify(fetchMock.mock.calls)).not.toContain('/renders');
  });

  it('"Lần xuất gần nhất" uses the fixed dark hero tokens, not the mode-dependent --primary', async () => {
    stubFetch({
      'GET /api/projects': [summary('muoi', 'Muỗi', { last_final: render() })],
      'GET /api/projects/muoi': brief,
    });
    page();
    const card = await screen.findByRole('region', { name: 'Lần xuất gần nhất' });
    expect(card).toHaveClass('bg-hero', 'text-on-hero');
    expect(card).not.toHaveClass('bg-primary');
    expect(card).not.toHaveClass('text-on-primary');
  });

  it('shows "—" for build time on an old render and a notice when nothing was ever rendered', async () => {
    stubFetch({
      'GET /api/projects': [
        summary('muoi', 'Muỗi', { last_render: render({ render_seconds: null, preview: true }) }),
      ],
      'GET /api/projects/muoi': brief,
    });
    const first = page();
    const card = await screen.findByRole('region', { name: 'Lần xuất gần nhất' });
    expect(within(card).getByText('—')).toBeVisible();
    expect(within(card).getByText(/Xem nhanh/)).toBeVisible();
    first.unmount();

    stubFetch({ 'GET /api/projects': [summary('muoi', 'Muỗi')], 'GET /api/projects/muoi': brief });
    page();
    expect(await screen.findByText('Chưa có lần xuất nào')).toBeVisible();
  });

  it('"Gần đây" lists up to 4 other projects and links to /projects', async () => {
    const user = userEvent.setup();
    stubFetch({
      'GET /api/projects': ['a', 'b', 'c', 'd', 'e', 'f'].map((s) => summary(s, `Dự án ${s}`)),
      'GET /api/projects/a': brief,
    });
    page();
    const recent = await screen.findByRole('region', { name: 'Gần đây' });
    const links = within(recent).getAllByRole('link', { name: /^Mở:/ });
    expect(links.map((l) => l.getAttribute('href'))).toEqual(['/p/b', '/p/c', '/p/d', '/p/e']);
    await user.click(within(recent).getByRole('link', { name: 'Xem tất cả' }));
    expect(await screen.findByText('trang dự án')).toBeVisible();
  });

  it('omits "Gần đây" when there is only one project', async () => {
    stubFetch({ 'GET /api/projects': [summary('muoi', 'Muỗi')], 'GET /api/projects/muoi': brief });
    page();
    await screen.findByRole('region', { name: 'Tiếp tục làm' });
    expect(screen.queryByRole('region', { name: 'Gần đây' })).toBeNull();
  });

  it('shows the empty state and its button opens the new-video dialog', async () => {
    const user = userEvent.setup();
    stubFetch({ 'GET /api/projects': [] });
    page();
    expect(await screen.findByRole('heading', { name: /Tạo video\s*đầu tiên/ })).toBeVisible();
    expect(screen.queryByRole('region', { name: 'Tiếp tục làm' })).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Tạo video' }));
    expect(await screen.findByRole('dialog', { name: 'Tạo video mới' })).toBeInTheDocument();
  });

  it('keeps working if the project detail request fails (dots just stay hidden)', async () => {
    stubFetch({
      'GET /api/projects': [summary('muoi', 'Muỗi')],
      'GET /api/projects/muoi': () => new Response('{}', { status: 500 }),
    });
    page();
    const card = await screen.findByRole('region', { name: 'Tiếp tục làm' });
    expect(within(card).getByRole('link', { name: 'Mở dự án' })).toBeVisible();
  });
});
