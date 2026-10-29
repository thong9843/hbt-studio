import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider } from '../components/Toast';
import { NewProjectProvider } from '../components/NewProjectDialog';
import { useRenderJob } from '../hooks/renderJob';
import { FakeEventSource, stubFetch } from '../test/fakes';
import { project } from '../test/project';
import { renderWithProviders } from '../test/render';
import { ProjectsPage } from './ProjectsPage';

afterEach(() => vi.unstubAllGlobals());

const render = (over: Record<string, unknown> = {}) => ({
  job_id: 'a',
  preview: false,
  fps: 50,
  duration: 83,
  created_at: '2026-10-22T10:00:00',
  video: null,
  ...over,
});
const summary = (slug: string, title: string, over: Record<string, unknown> = {}) => ({
  slug,
  title,
  updated_at: '2026-10-22T10:00:00',
  thumb: null,
  cover: null,
  last_render: null,
  last_final: null,
  error: null,
  ...over,
});
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

function page() {
  return renderWithProviders(
    <ToastProvider>
      <NewProjectProvider>
        <Routes>
          <Route path="/" element={<ProjectsPage />} />
          <Route path="/p/:slug" element={<p>trang soạn</p>} />
          <Route path="/postv/:slug" element={<p>trang PostV</p>} />
        </Routes>
      </NewProjectProvider>
    </ToastProvider>,
    '/',
  );
}

const card = (title: string) =>
  screen.getByRole('link', { name: `Mở: ${title}` }).closest('li') as HTMLElement;

describe('ProjectsPage', () => {
  it('shows the three status labels from last_final / last_render', async () => {
    stubFetch({
      'GET /api/projects': [
        summary('a', 'Bản đẹp', {
          last_final: render({ fps: 60 }),
          last_render: render({ preview: true }),
        }),
        summary('b', 'Chỉ xem nhanh', { last_render: render({ preview: true }) }),
        summary('c', 'Mới tạo'),
      ],
    });
    page();
    await screen.findByText('Bản đẹp');
    expect(within(card('Bản đẹp')).getByText('Đã xuất · 60 fps')).toBeInTheDocument();
    expect(within(card('Chỉ xem nhanh')).getByText('Đã xem nhanh')).toBeInTheDocument();
    expect(within(card('Mới tạo')).getByText('Chưa dựng')).toBeInTheDocument();
  });

  it('marks PostV projects with a badge and opens them on /postv', async () => {
    stubFetch({
      'GET /api/projects': [
        summary('bai', 'Bài PostV', { kind: 'postv' }),
        summary('muoi', 'Muỗi', { kind: 'video' }),
      ],
    });
    page();
    await screen.findByText('Bài PostV');
    expect(within(card('Bài PostV')).getByText('PostV')).toBeInTheDocument();
    expect(within(card('Muỗi')).queryByText('PostV')).toBeNull();
    expect(screen.getByRole('link', { name: 'Mở: Bài PostV' })).toHaveAttribute(
      'href',
      '/postv/bai',
    );
    expect(screen.getByRole('link', { name: 'Mở: Muỗi' })).toHaveAttribute('href', '/p/muoi');
  });

  it('duplicating a PostV project opens the copy on /postv', async () => {
    const user = userEvent.setup();
    stubFetch({
      'GET /api/projects': [summary('bai', 'Bài PostV', { kind: 'postv' })],
      'POST /api/projects/bai/duplicate': {
        version: 1,
        kind: 'postv',
        slug: 'bai-ban-sao',
        title: 'Bài PostV (bản sao)',
      },
    });
    page();
    await screen.findByText('Bài PostV');
    await user.click(
      within(card('Bài PostV')).getByRole('button', { name: 'Thao tác: Bài PostV' }),
    );
    await user.click(await screen.findByRole('menuitem', { name: 'Nhân bản' }));
    expect(await screen.findByText('trang PostV')).toBeInTheDocument();
  });

  it('uses the cover, then scene 1, then the HBT tile; images are lazy', async () => {
    stubFetch({
      'GET /api/projects': [
        summary('a', 'Có bìa', {
          cover: '/api/files/a/cover_9x16.jpg',
          thumb: '/api/files/a/1.png',
        }),
        summary('b', 'Chỉ ảnh', { thumb: '/api/files/b/1.png' }),
        summary('c', 'Trống'),
      ],
    });
    page();
    await screen.findByText('Có bìa');
    const img = (t: string) => card(t).querySelector('img') as HTMLImageElement;
    expect(img('Có bìa')).toHaveAttribute('src', '/api/files/a/cover_9x16.jpg');
    expect(img('Có bìa')).toHaveAttribute('loading', 'lazy');
    expect(img('Có bìa')).toHaveAttribute('decoding', 'async');
    expect(img('Chỉ ảnh')).toHaveAttribute('src', '/api/files/b/1.png');
    expect(img('Trống')).toHaveAttribute('src', '/brand/hbt-logo-mark.png');
    expect(within(card('Trống')).getByText('Chưa có ảnh')).toBeInTheDocument();
  });

  it('falls back to the HBT tile once when the image fails to load', async () => {
    stubFetch({
      'GET /api/projects': [
        summary('a', 'Ảnh hỏng', { thumb: '/api/files/projects/a/images/x.png' }),
      ],
    });
    page();
    await screen.findByText('Ảnh hỏng');
    const img = card('Ảnh hỏng').querySelector('img') as HTMLImageElement;
    expect(img).toHaveAttribute('src', '/api/files/projects/a/images/x.png');
    fireEvent.error(img);
    const after = card('Ảnh hỏng').querySelector('img') as HTMLImageElement;
    expect(after).toHaveAttribute('src', '/brand/hbt-logo-mark.png');
    expect(within(card('Ảnh hỏng')).getByText('Chưa có ảnh')).toBeInTheDocument();
    // Lỗi của ô HBT không làm vòng lặp: vẫn là ô HBT.
    fireEvent.error(after);
    expect(card('Ảnh hỏng').querySelector('img')).toHaveAttribute(
      'src',
      '/brand/hbt-logo-mark.png',
    );
  });

  it('links the card to the editor and shows the date', async () => {
    stubFetch({ 'GET /api/projects': [summary('muoi', 'Muỗi')] });
    page();
    expect(await screen.findByRole('link', { name: 'Muỗi' })).toHaveAttribute('href', '/p/muoi');
    expect(within(card('Muỗi')).getByText('22/10/2026')).toBeInTheDocument();
  });

  it('shows skeletons while loading, then removes them', async () => {
    stubFetch({ 'GET /api/projects': [summary('a', 'A')] });
    page();
    expect(screen.getAllByRole('status', { name: 'Đang tải' }).length).toBeGreaterThan(0);
    await screen.findByText('A');
    expect(screen.queryByRole('status', { name: 'Đang tải' })).toBeNull();
  });

  it('shows the empty state with three steps and a create button', async () => {
    const user = userEvent.setup();
    stubFetch({ 'GET /api/projects': [] });
    page();
    expect(await screen.findByRole('heading', { name: /Tạo video\s*đầu tiên/ })).toBeVisible();
    for (const step of ['Kịch bản', 'Ảnh 9:16', 'Giọng + nhạc'])
      expect(screen.getByText(step)).toBeInTheDocument();
    // Một nút chính mỗi màn: không có nút thứ hai ở thanh đầu.
    expect(screen.getAllByRole('button', { name: /Tạo video/ })).toHaveLength(1);
    await user.click(screen.getByRole('button', { name: 'Tạo video' }));
    expect(await screen.findByRole('dialog', { name: 'Tạo video mới' })).toBeInTheDocument();
  });

  it('shows the header create button when there are projects', async () => {
    stubFetch({ 'GET /api/projects': [summary('a', 'A')] });
    page();
    await screen.findByText('A');
    expect(screen.getByRole('button', { name: 'Tạo video mới' })).toBeInTheDocument();
  });

  it('duplicates from the ⋯ menu and opens the copy', async () => {
    const user = userEvent.setup();
    const dup = vi.fn(() => json(project({ slug: 'a-ban-sao', title: 'A (bản sao)' }), 201));
    stubFetch({
      'GET /api/projects': [summary('a', 'A')],
      'POST /api/projects/a/duplicate': dup,
    });
    page();
    await screen.findByText('A');
    await user.click(screen.getByRole('button', { name: 'Thao tác: A' }));
    await user.click(screen.getByRole('menuitem', { name: 'Nhân bản' }));
    expect(await screen.findByText('trang soạn')).toBeInTheDocument();
    expect(dup).toHaveBeenCalledTimes(1);
  });

  it('asks before deleting; Cancel keeps the project', async () => {
    const user = userEvent.setup();
    const del = vi.fn(() => new Response(null, { status: 204 }));
    stubFetch({ 'GET /api/projects': [summary('a', 'A')], 'DELETE /api/projects/a': del });
    page();
    await screen.findByText('A');
    await user.click(screen.getByRole('button', { name: 'Thao tác: A' }));
    await user.click(screen.getByRole('menuitem', { name: 'Xoá' }));
    const dialog = await screen.findByRole('alertdialog', { name: 'Xoá dự án?' });
    expect(dialog).toHaveTextContent('"A"');
    await user.click(within(dialog).getByRole('button', { name: 'Huỷ' }));
    expect(del).not.toHaveBeenCalled();
  });

  it('deletes after confirmation', async () => {
    const user = userEvent.setup();
    const del = vi.fn(() => new Response(null, { status: 204 }));
    stubFetch({ 'GET /api/projects': [summary('a', 'A')], 'DELETE /api/projects/a': del });
    page();
    await screen.findByText('A');
    await user.click(screen.getByRole('button', { name: 'Thao tác: A' }));
    await user.click(screen.getByRole('menuitem', { name: 'Xoá' }));
    const dialog = await screen.findByRole('alertdialog');
    await user.click(within(dialog).getByRole('button', { name: 'Xoá' }));
    await waitFor(() => expect(del).toHaveBeenCalledTimes(1));
  });

  it('a 409 on delete (rendering) is reported, not swallowed', async () => {
    const user = userEvent.setup();
    stubFetch({
      'GET /api/projects': [summary('a', 'A')],
      'DELETE /api/projects/a': () => json({ detail: 'Project đang được dựng' }, 409),
    });
    page();
    await screen.findByText('A');
    await user.click(screen.getByRole('button', { name: 'Thao tác: A' }));
    await user.click(screen.getByRole('menuitem', { name: 'Xoá' }));
    const dialog = await screen.findByRole('alertdialog');
    await user.click(within(dialog).getByRole('button', { name: 'Xoá' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Project đang được dựng');
    expect(screen.getByText('A')).toBeInTheDocument();
  });

  it('locks Nhân bản / Xoá of the project being rendered only, and unlocks when the job ends', async () => {
    const user = userEvent.setup();
    FakeEventSource.instances = [];
    vi.stubGlobal('EventSource', FakeEventSource);
    stubFetch({
      'GET /api/projects': [summary('a', 'A'), summary('b', 'B')],
      'POST /api/projects/a/render': { job_id: 'j1' },
      'GET /api/jobs/j1': { id: 'j1', project: 'a', status: 'done', progress: 100, step: '' },
    });
    function Starter() {
      const rj = useRenderJob();
      return (
        <button type="button" onClick={() => void rj.start('a', { preview: true })}>
          go
        </button>
      );
    }
    renderWithProviders(
      <ToastProvider>
        <NewProjectProvider>
          <Starter />
          <ProjectsPage />
        </NewProjectProvider>
      </ToastProvider>,
    );
    await screen.findByText('A');
    await user.click(screen.getByRole('button', { name: 'go' }));
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));

    await user.click(screen.getByRole('button', { name: 'Thao tác: A' }));
    expect(screen.getByRole('menuitem', { name: /Nhân bản/ })).toBeDisabled();
    expect(screen.getByRole('menuitem', { name: /Xoá/ })).toBeDisabled();
    expect(screen.getByRole('menuitem', { name: /Xoá/ })).toHaveAttribute('title', 'Đang dựng');
    await user.keyboard('{Escape}');

    await user.click(screen.getByRole('button', { name: 'Thao tác: B' }));
    expect(screen.getByRole('menuitem', { name: 'Nhân bản' })).toBeEnabled();
    await user.keyboard('{Escape}');

    act(() => FakeEventSource.instances[0].emit('end', { status: 'done' }));
    await waitFor(async () => {
      await user.click(screen.getByRole('button', { name: 'Thao tác: A' }));
      expect(screen.getByRole('menuitem', { name: 'Xoá' })).toBeEnabled();
    });
  });

  it('flags an unreadable project and still lets it be deleted', async () => {
    stubFetch({ 'GET /api/projects': [summary('x', 'x', { error: 'JSON hỏng' })] });
    page();
    await screen.findByText('Không đọc được project');
    expect(screen.getByRole('button', { name: 'Thao tác: x' })).toBeInTheDocument();
  });

  it('shows the API error with a retry button', async () => {
    const user = userEvent.setup();
    let calls = 0;
    stubFetch({
      'GET /api/projects': () => (calls++ === 0 ? json({ detail: 'lỗi' }, 500) : json([])),
    });
    page();
    await user.click(await screen.findByRole('button', { name: 'Thử lại' }));
    expect(await screen.findByRole('heading', { name: /Tạo video\s*đầu tiên/ })).toBeVisible();
  });
});
