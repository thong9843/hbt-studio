import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider } from '../components/Toast';
import { stubFetch } from '../test/fakes';
import { renderWithProviders } from '../test/render';
import { AssetHubPage } from './AssetHubPage';

afterEach(() => vi.unstubAllGlobals());

describe('AssetHubPage (Thư viện tài nguyên)', () => {
  it('switches between the 4 resource categories (no renders tab), lists files, and deletes a file', async () => {
    let stickers = [
      {
        name: 'shock.png',
        category: 'stickers',
        kind: 'image',
        size: 2048,
        modified_at: '2026-11-12T08:00:00Z',
        url: '/api/asset-hub/files/stickers/shock.png',
      },
    ];
    const music = [
      {
        name: 'chill-bgm.mp3',
        category: 'music',
        kind: 'audio',
        size: 102400,
        modified_at: '2026-11-12T08:00:00Z',
        url: '/api/asset-hub/files/music/chill-bgm.mp3',
      },
    ];

    stubFetch({
      'GET /api/asset-hub/stickers': () =>
        new Response(JSON.stringify({ category: 'stickers', items: stickers }), {
          headers: { 'Content-Type': 'application/json' },
        }),
      'GET /api/asset-hub/music': () =>
        new Response(JSON.stringify({ category: 'music', items: music }), {
          headers: { 'Content-Type': 'application/json' },
        }),
      'GET /api/asset-hub/backgrounds': { category: 'backgrounds', items: [] },
      'GET /api/asset-hub/watermarks': { category: 'watermarks', items: [] },
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

    expect(await screen.findByText('shock.png')).toBeVisible();
    // Không còn tab "Video đã làm"
    expect(screen.queryByRole('tab', { name: /Video đã làm/i })).toBeNull();

    // Chuyển tab Nhạc nền
    await user.click(screen.getByRole('tab', { name: /Nhạc nền/ }));
    expect(await screen.findByText('chill-bgm.mp3')).toBeVisible();

    // Chuyển lại Sticker & Meme và xoá tệp
    await user.click(screen.getByRole('tab', { name: /Sticker/ }));
    expect(await screen.findByText('shock.png')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Xoá: shock.png' }));

    await waitFor(() => expect(screen.queryByText('shock.png')).toBeNull());
    expect(screen.getByText('Chưa có tệp nào trong mục này.')).toBeVisible();
  });
});
