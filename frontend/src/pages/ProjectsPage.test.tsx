import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { stubFetch } from '../test/fakes';
import { project } from '../test/project';
import { renderWithProviders } from '../test/render';
import { ProjectsPage } from './ProjectsPage';

afterEach(() => vi.unstubAllGlobals());

const health = { ok: true, ffmpeg: true, whisper: false, gpu: false, missing: [] };
const summary = (slug: string, title: string, last_render: unknown = null) => ({
  slug,
  title,
  updated_at: '2026-10-22T10:00:00',
  thumb: null,
  last_render,
  error: null,
});

function page() {
  return renderWithProviders(
    <Routes>
      <Route path="/" element={<ProjectsPage />} />
      <Route path="/p/:slug" element={<p>trang soạn</p>} />
    </Routes>,
  );
}

describe('ProjectsPage', () => {
  it('lists projects with their render state and the default thumbnail', async () => {
    stubFetch({
      'GET /api/health': health,
      'GET /api/projects': [
        summary('muoi', 'Muỗi', {
          job_id: 'a',
          preview: false,
          duration: 83,
          created_at: 'x',
          video: null,
          fps: 50,
        }),
        summary('chuon', 'Chuồn chuồn'),
      ],
    });
    page();
    expect(await screen.findByRole('link', { name: 'Muỗi' })).toHaveAttribute('href', '/p/muoi');
    expect(screen.getByText(/Đã xuất · 1:23/)).toBeInTheDocument();
    expect(screen.getByText('Chưa xuất')).toBeInTheDocument();
    const imgs = document.querySelectorAll('li img');
    expect(imgs[0]).toHaveAttribute('src', '/brand/hay-biet-tuot_avatar.png');
  });

  it('shows the empty state', async () => {
    stubFetch({ 'GET /api/health': health, 'GET /api/projects': [] });
    page();
    expect(await screen.findByText(/Chưa có video nào/)).toBeInTheDocument();
  });

  it('creates a video from the dialog and opens it', async () => {
    const user = userEvent.setup();
    const create = vi.fn((_url: string, init?: RequestInit) => {
      void init;
      return new Response(JSON.stringify(project({ slug: 'video-moi', title: 'Video mới' })), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      });
    });
    stubFetch({ 'GET /api/health': health, 'GET /api/projects': [], 'POST /api/projects': create });
    page();
    await user.click(await screen.findByRole('button', { name: 'Tạo video mới' }));
    const dialog = screen.getByRole('dialog');
    expect(dialog).toBeInTheDocument();
    await user.type(screen.getByLabelText('Tiêu đề'), 'Video mới');
    await user.click(screen.getByRole('button', { name: 'Tạo' }));
    expect(await screen.findByText('trang soạn')).toBeInTheDocument();
    expect(JSON.parse(String(create.mock.calls[0][1]?.body))).toEqual({
      title: 'Video mới',
      series: '',
      scene_count: 8,
    });
  });

  it('shows the API error inside the dialog', async () => {
    const user = userEvent.setup();
    stubFetch({
      'GET /api/health': health,
      'GET /api/projects': [],
      'POST /api/projects': () =>
        new Response(JSON.stringify({ detail: 'Tiêu đề trùng' }), {
          status: 409,
          headers: { 'Content-Type': 'application/json' },
        }),
    });
    page();
    await user.click(await screen.findByRole('button', { name: 'Tạo video mới' }));
    await user.type(screen.getByLabelText('Tiêu đề'), 'A');
    await user.click(screen.getByRole('button', { name: 'Tạo' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Tiêu đề trùng'));
  });
});
