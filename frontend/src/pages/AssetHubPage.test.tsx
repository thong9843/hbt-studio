import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider } from '../components/Toast';
import { stubFetch } from '../test/fakes';
import { renderWithProviders } from '../test/render';
import { AssetHubPage } from './AssetHubPage';

afterEach(() => vi.unstubAllGlobals());

describe('AssetHubPage (Thư viện tài nguyên)', () => {
  it('switches between resource tabs and renders tab, lists real items, and deletes a file', async () => {
    let stickers = [
      {
        name: 'shock.png',
        category: 'stickers',
        kind: 'image',
        size: 2048,
        modified_at: '2026-11-12T08:00:00Z',
        url: '/api/asset-hub/files/stickers/shock.png',
        source: 'assets',
      },
    ];
    const music = [
      {
        name: 'chill-bgm.mp3',
        category: 'music',
        kind: 'audio',
        size: 102400,
        modified_at: '2026-11-12T08:00:00Z',
        url: '/api/asset-hub/file/library/music/chill-bgm.mp3',
        title: 'Lo-Fi Chill',
        artist: 'Kulakovka',
        moods: ['chill'],
        source: 'library',
      },
    ];
    const renders = [
      {
        id: 'core:demo:job1:video.mp4',
        slug: 'demo',
        title: 'Video Demo 9:16',
        engine: 'core',
        duration_sec: 42,
        size_mb: 3.5,
        publish_text: 'Caption test #HBT',
        created_at: '2026-11-15T10:00:00Z',
        video_url: '/api/renders/media/core1?kind=video',
        cover_url: null,
      },
    ];

    stubFetch({
      'GET /api/asset-hub/music': () =>
        new Response(JSON.stringify({ category: 'music', items: music }), {
          headers: { 'Content-Type': 'application/json' },
        }),
      'GET /api/asset-hub/stickers': () =>
        new Response(JSON.stringify({ category: 'stickers', items: stickers }), {
          headers: { 'Content-Type': 'application/json' },
        }),
      'GET /api/asset-hub/stickman': () =>
        new Response(
          JSON.stringify({
            category: 'stickman',
            items: [
              {
                name: 'explain.png',
                category: 'stickman',
                kind: 'image',
                size: 1024,
                modified_at: '2026-11-17T08:00:00Z',
                url: '/api/asset-hub/file/library/stickman/poses/explain.png',
                source: 'library',
                title: 'Giải thích / Chỉ bảng',
              },
            ],
          }),
          { headers: { 'Content-Type': 'application/json' } },
        ),
      'GET /api/asset-hub/backgrounds': { category: 'backgrounds', items: [] },
      'GET /api/asset-hub/memes': { category: 'memes', items: [] },
      'GET /api/asset-hub/watermarks': { category: 'watermarks', items: [] },
      'GET /api/renders': { items: renders },
      'DELETE /api/asset-hub/stickers/shock.png': () => {
        stickers = [];
        return new Response(JSON.stringify({ ok: true, deleted: 'shock.png' }), {
          headers: { 'Content-Type': 'application/json' },
        });
      },
    });

    const user = userEvent.setup();
    renderWithProviders(
      <ToastProvider>
        <AssetHubPage />
      </ToastProvider>,
    );

    // Mặc định mở tab Video đã xuất, kiểm tra có Video Demo 9:16
    const section = await screen.findByRole('region', { name: 'Video đã xuất trên hệ thống' });
    expect(await within(section).findByText('Video Demo 9:16')).toBeVisible();

    // Chuyển tab Nhạc nền dạng danh sách
    await user.click(screen.getByRole('tab', { name: /Nhạc nền/ }));
    expect(await screen.findByText('Lo-Fi Chill')).toBeVisible();
    expect(screen.getByText('Kulakovka')).toBeVisible();

    // Chuyển tab Sticker và xoá tệp
    await user.click(screen.getByRole('tab', { name: /Sticker/ }));
    expect(await screen.findByText('shock.png')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Xóa shock.png' }));
    await waitFor(() => expect(screen.queryByText('shock.png')).toBeNull());
    expect(screen.getByText('Chưa có tệp nào trong mục này.')).toBeVisible();
  });
});
