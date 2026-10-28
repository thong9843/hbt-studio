import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { NewProjectProvider } from '../components/NewProjectDialog';
import { stubFetch } from '../test/fakes';
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
    <NewProjectProvider>
      <Routes>
        <Route path="/" element={<ProjectsPage />} />
        <Route path="/p/:slug" element={<p>trang soạn</p>} />
      </Routes>
    </NewProjectProvider>,
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

  it('opens the new-video dialog from the empty state', async () => {
    const user = userEvent.setup();
    stubFetch({ 'GET /api/health': health, 'GET /api/projects': [] });
    page();
    await screen.findByText('Tạo video đầu tiên');
    await user.click(screen.getByRole('button', { name: 'Tạo video mới' }));
    expect(await screen.findByRole('dialog', { name: 'Tạo video mới' })).toBeInTheDocument();
  });
});
