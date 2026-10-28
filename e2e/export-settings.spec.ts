import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { expect, test } from '@playwright/test';

import { vi } from '../frontend/src/i18n/vi';

const API = 'http://127.0.0.1:8000/api';
const SAMPLE = join(process.cwd(), 'workspace', 'samples', 'muoi');

test('Xem nhanh từ Soạn video tự dựng ở tab Xuất; thẻ trái hiện tiến độ và Huỷ dừng job', async ({
  page,
  request,
}) => {
  test.setTimeout(120_000);
  let slug = '';
  try {
    const created = await request.post(`${API}/projects`, {
      data: { title: `E2E xuất ${Date.now()}`, scene_count: 3 },
    });
    expect(created.ok()).toBeTruthy();
    slug = (await created.json()).slug;
    for (let i = 0; i < 3; i++) {
      const res = await request.post(`${API}/projects/${slug}/assets`, {
        multipart: {
          kind: 'image',
          scene_index: String(i),
          file: {
            name: `scene-0${i + 1}.png`,
            mimeType: 'image/png',
            buffer: readFileSync(join(SAMPLE, 'images', `scene-0${i + 1}.png`)),
          },
        },
      });
      expect(res.ok()).toBeTruthy();
    }
    const voice = await request.post(`${API}/projects/${slug}/assets`, {
      multipart: {
        kind: 'voice',
        file: {
          name: 'voice.mp3',
          mimeType: 'audio/mpeg',
          buffer: readFileSync(join(SAMPLE, 'voice.mp3')),
        },
      },
    });
    expect(voice.ok()).toBeTruthy();

    // Kiểm tra chặn nếu cảnh nào chưa có lời đọc.
    const project = await (await request.get(`${API}/projects/${slug}`)).json();
    project.scenes = project.scenes.map((s: Record<string, unknown>) => ({
      ...s,
      voice: 'Muỗi đốt người.',
    }));
    expect((await request.put(`${API}/projects/${slug}`, { data: project })).ok()).toBeTruthy();

    await page.goto(`/p/${slug}`);
    const fast = page.getByRole('button', { name: vi.compose.preview.fast, exact: true });
    await expect(fast).toBeEnabled();
    await fast.click();

    // Tab Xuất video tự dựng Xem nhanh; thẻ tiến độ ở thanh trái.
    await page.waitForURL(`**/p/${slug}/export`);
    const card = page.getByRole('status', { name: vi.nav.renderProgress });
    await expect(card).toBeVisible();

    // Đổi sang màn khác: thẻ vẫn còn (job toàn cục).
    await page.getByRole('link', { name: vi.nav.settings }).click();
    await expect(card).toBeVisible();

    await card.getByRole('button', { name: vi.nav.cancelRender }).click();
    await expect(card).toBeHidden({ timeout: 30_000 });

    await page.goto(`/p/${slug}/export`);
    await expect(page.getByRole('heading', { name: vi.export.title })).toBeVisible();
    // Huỷ xong không còn job chạy: nút dựng bấm lại được.
    await expect(page.getByRole('button', { name: vi.export.fast, exact: true })).toBeEnabled({
      timeout: 30_000,
    });
  } finally {
    if (slug) await request.delete(`${API}/projects/${slug}`);
  }
});

test('Cài đặt: đổi FPS mặc định, Lưu, tải lại vẫn còn; khôi phục giá trị cũ', async ({
  page,
  request,
}) => {
  const original = await (await request.get(`${API}/settings/app`)).json();
  const target = original.default_fps === 60 ? 30 : 60;
  try {
    await page.goto('/settings');
    await expect(page.getByRole('heading', { name: vi.settings.title })).toBeVisible();
    await page.getByRole('button', { name: `${target} fps`, exact: true }).click();
    await expect(page.getByText(vi.settings.dirty)).toBeVisible();
    await page.getByRole('button', { name: vi.settings.save, exact: true }).click();
    await expect(page.getByText(vi.settings.saved, { exact: true })).toBeVisible();

    await page.reload();
    await expect(page.getByRole('button', { name: `${target} fps`, exact: true })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  } finally {
    await request.put(`${API}/settings/app`, { data: original });
  }
});
