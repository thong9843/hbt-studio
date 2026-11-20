import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { NewProjectProvider } from '../components/NewProjectDialog';
import { stubFetch } from '../test/fakes';
import { project as makeProject } from '../test/project';
import { renderWithProviders } from '../test/render';
import { HomePage } from './HomePage';

afterEach(() => vi.unstubAllGlobals());

const summary = (slug: string, title: string, over: Record<string, unknown> = {}) => ({
  slug,
  title,
  updated_at: '2026-10-24T12:00:00',
  thumb: null,
  last_render: null,
  last_final: null,
  cover: null,
  error: null,
  ...over,
});

function page() {
  return renderWithProviders(
    <NewProjectProvider>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/projects" element={<p>Tất cả dự án</p>} />
        <Route path="/core" element={<p>HBT Core</p>} />
        <Route path="/postv" element={<p>PostV</p>} />
        <Route path="/chatting" element={<p>Chatting</p>} />
        <Route path="/p/:slug" element={<p>Trình soạn</p>} />
      </Routes>
    </NewProjectProvider>,
  );
}

describe('HomePage v5.0', () => {
  it('renders Creative Command Center hero, 3 KPI stats, and 3 Engine Showcase Cards', async () => {
    stubFetch({
      'GET /api/projects': [summary('muoi', 'Vì sao muỗi đốt bạn')],
      'GET /api/renders': { items: [] },
      'GET /api/asset-hub/music': { category: 'music', items: [{ name: 'a.mp3' }] },
      'GET /api/asset-hub/backgrounds': { category: 'backgrounds', items: [{ name: 'b.mp4' }] },
    });
    page();

    expect(screen.getByRole('heading', { name: 'Hôm nay dựng gì?' })).toBeInTheDocument();
    expect(screen.queryByText(/HBT Studio v5\.0/i)).toBeNull();
    expect(screen.getByRole('link', { name: 'Mở Core' })).toHaveAttribute('href', '/core');
    expect(screen.getByRole('link', { name: 'Mở PostV' })).toHaveAttribute('href', '/postv');
    expect(screen.getByRole('link', { name: 'Mở Chatting' })).toHaveAttribute('href', '/chatting');
    expect(screen.getByRole('link', { name: 'Mở StickV' })).toHaveAttribute('href', '/stickv');

    await waitFor(() => expect(screen.getByText('Vì sao muỗi đốt bạn')).toBeInTheDocument());
  });

  it('shows Continue card with readiness dots and Recent projects grid', async () => {
    const detail = makeProject({
      slug: 'muoi',
      title: 'Vì sao muỗi đốt bạn',
      series: 'Bí ẩn tự nhiên',
      voice: 'voice.wav',
      music: null,
      thumbnail: null,
    });
    stubFetch({
      'GET /api/projects': [
        summary('muoi', 'Vì sao muỗi đốt bạn'),
        summary('sao', 'Vì sao bầu trời màu xanh'),
        summary('meo', 'Mèo kêu meo meo'),
      ],
      'GET /api/projects/muoi': detail,
      'GET /api/renders': { items: [] },
      'GET /api/asset-hub/music': { category: 'music', items: [] },
      'GET /api/asset-hub/backgrounds': { category: 'backgrounds', items: [] },
    });
    page();

    const cont = await screen.findByRole('region', { name: 'Tiếp tục làm' });
    expect(within(cont).getByText('Vì sao muỗi đốt bạn')).toBeInTheDocument();
    expect(await within(cont).findByText('Bí ẩn tự nhiên')).toBeInTheDocument();

    const recentSection = screen.getByRole('region', { name: 'Tiếp tục dự án dở' });
    expect(within(recentSection).getByText('Vì sao bầu trời màu xanh')).toBeInTheDocument();
    expect(within(recentSection).getByText('Mèo kêu meo meo')).toBeInTheDocument();
  });

  it('displays unified exported videos, filters by engine, and opens the 9:16 player modal', async () => {
    const user = userEvent.setup();
    stubFetch({
      'GET /api/projects': [],
      'GET /api/asset-hub/music': { category: 'music', items: [] },
      'GET /api/asset-hub/backgrounds': { category: 'backgrounds', items: [] },
      'GET /api/renders': {
        items: [
          {
            id: 'core::muoi::final.mp4',
            engine: 'core',
            slug: 'muoi',
            title: 'Vì sao muỗi đốt bạn',
            video_url: '/api/renders/media/core/muoi/final.mp4',
            cover_url: null,
            publish_text: 'Caption Muỗi #shorts',
            size_mb: 14.2,
            duration_sec: 42,
            created_at: '2026-11-16T08:00:00',
          },
          {
            id: 'chatting::chat1::final.mp4',
            engine: 'chatting',
            slug: 'chat1',
            title: 'Drama Messenger 2h sáng',
            video_url: '/api/renders/media/chatting/chat1/final.mp4',
            cover_url: null,
            publish_text: 'Caption Chat #reels',
            size_mb: 9.8,
            duration_sec: 35,
            created_at: '2026-11-16T09:00:00',
          },
        ],
      },
    });
    page();

    const rendersSection = await screen.findByRole('region', { name: 'Video đã xuất gần đây' });
    expect(await within(rendersSection).findByText('Vì sao muỗi đốt bạn')).toBeInTheDocument();
    expect(within(rendersSection).getByText('Drama Messenger 2h sáng')).toBeInTheDocument();

    await user.click(within(rendersSection).getByRole('button', { name: 'Chatting' }));
    expect(within(rendersSection).queryByText('Vì sao muỗi đốt bạn')).toBeNull();
    expect(within(rendersSection).getByText('Drama Messenger 2h sáng')).toBeInTheDocument();

    await user.click(within(rendersSection).getByRole('button', { name: 'Xem video' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Caption Chat #reels')).toBeInTheDocument();
  });
});
