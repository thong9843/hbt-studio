import { expect, test } from '@playwright/test';

import { vi } from '../frontend/src/i18n/vi';
import { deleteProject } from './helpers';

const API = 'http://127.0.0.1:8000/api';

test('nút Sáng/Tối: nhớ lựa chọn và áp trước lần vẽ đầu sau khi tải lại', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light' });
  await page.goto('/');
  const toDark = page.getByRole('button', { name: vi.nav.theme.toDark });
  await expect(toDark).toHaveAttribute('aria-pressed', 'false');
  await toDark.click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');

  // Tải lại: script trong <head> đã đặt data-theme trước khi React vẽ.
  await page.reload({ waitUntil: 'commit' });
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await expect(page.getByRole('button', { name: vi.nav.theme.toLight })).toHaveAttribute(
    'aria-pressed',
    'true',
  );

  await page.getByRole('button', { name: vi.nav.theme.toLight }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await page.evaluate(() => localStorage.removeItem('hbt-theme'));
});

test('màn Âm thanh: ba thẻ, xem trước 9:16, Không nhạc', async ({ page, request }) => {
  const title = `E2E âm thanh ${Date.now()}`;
  let slug = '';
  try {
    const res = await request.post(`${API}/projects`, { data: { title, scene_count: 3 } });
    expect(res.ok()).toBeTruthy();
    slug = (await res.json()).slug;

    await page.goto(`/p/${slug}/audio`);
    await expect(page.getByRole('heading', { name: vi.audio.voice.title })).toBeVisible();
    await expect(page.getByRole('heading', { name: vi.audio.start.title })).toBeVisible();
    await expect(page.getByRole('heading', { name: vi.audio.music.title })).toBeVisible();
    await expect(page.getByRole('button', { name: vi.audio.music.noMusic })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await expect(page.getByText(vi.audio.music.noMusicNote)).toBeVisible();
    await expect(page.getByText(vi.compose.preview.position(1, 3))).toBeVisible();
    await page.getByRole('button', { name: vi.compose.preview.next }).click();
    await expect(page.getByText(vi.compose.preview.position(2, 3))).toBeVisible();
  } finally {
    await deleteProject(request, slug);
  }
});
