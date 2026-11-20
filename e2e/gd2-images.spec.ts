import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { expect, test } from '@playwright/test';

import { vi } from '../frontend/src/i18n/vi';
import { API, deleteProject, solidPng } from './helpers';

const FIXTURE = join(process.cwd(), 'backend', 'tests', 'data', 'hbt-draft.sample.json');
const COLOURS: [number, number, number][] = [
  [200, 60, 50],
  [50, 160, 90],
  [60, 90, 200],
];

test('Bước Ảnh đường tay: thả 3 ảnh → Duyệt → tải lại còn duyệt → đổi ảnh cảnh 2 thì hết duyệt', async ({
  page,
  request,
}) => {
  test.setTimeout(90_000);
  const draft = JSON.parse(readFileSync(FIXTURE, 'utf-8'));
  let slug = '';
  try {
    const created = await request.post(`${API}/gd2/draft/create`, { data: { draft } });
    expect(created.ok()).toBeTruthy();
    slug = (await created.json()).slug;

    await page.goto(`/p/${slug}`);
    // Mục Ảnh ở thanh trái, giữa Soạn video và Âm thanh.
    const group = page.getByRole('group', { name: vi.nav.openProject });
    await expect(group.getByRole('link')).toHaveText([
      vi.nav.compose,
      vi.nav.images,
      vi.nav.audio,
      vi.nav.export,
    ]);
    await group.getByRole('link', { name: vi.nav.images }).click();
    await expect(page.getByRole('heading', { name: vi.gd2.images.title })).toBeVisible();
    await expect(page.getByTestId('prompt-1')).toHaveText(draft.scenes[1].image_prompt);

    const approve = page.getByRole('button', { name: /^Duyệt ảnh/ });
    await expect(approve).toBeDisabled(); // chưa có ảnh nào

    for (const [i, rgb] of COLOURS.entries()) {
      await page.getByTestId(`image-file-${i}`).setInputFiles({
        name: `a${i}.png`,
        mimeType: 'image/png',
        buffer: solidPng(540, 960, rgb),
      });
      await expect(page.getByText(vi.gd2.images.stats(i + 1, 3, 0))).toBeVisible();
    }
    await expect(approve).toBeEnabled();
    await approve.click();
    await expect(page.getByText(vi.gd2.images.stats(3, 3, 3))).toBeVisible();
    await expect(page.getByRole('button', { name: vi.gd2.images.unapprove })).toBeVisible();

    // Tải lại: dấu duyệt nằm trên đĩa.
    await page.reload();
    await expect(page.getByText(vi.gd2.images.stats(3, 3, 3))).toBeVisible();
    const saved = await (await request.get(`${API}/projects/${slug}/draft`)).json();
    expect(saved.images_approved).toBe(true);

    // Tab Xuất không nhắc khi đã duyệt.
    await page.goto(`/p/${slug}/export`);
    await expect(page.getByRole('heading', { name: vi.export.title })).toBeVisible();
    await expect(page.getByText(vi.gd2.images.exportReminder)).toHaveCount(0);

    // Đổi ảnh cảnh 2 → chỉ cảnh đó hết duyệt, tab Xuất nhắc nhưng không chặn.
    await page.goto(`/p/${slug}/images`);
    await page.getByTestId('image-file-1').setInputFiles({
      name: 'b.png',
      mimeType: 'image/png',
      buffer: solidPng(540, 960, [240, 220, 20]),
    });
    await expect(page.getByText(vi.gd2.images.stats(3, 3, 2))).toBeVisible();
    await expect(page.getByRole('button', { name: /^Duyệt ảnh/ })).toBeEnabled();
    await page.goto(`/p/${slug}/export`);
    await expect(page.getByText(vi.gd2.images.exportReminder)).toBeVisible();
    await expect(
      page.getByRole('link', { name: vi.gd2.images.exportReminderLink }),
    ).toHaveAttribute('href', `/p/${slug}/images`);
  } finally {
    await deleteProject(request, slug);
  }
});

test('Dự án thường: không có mục Ảnh và không lỗi', async ({ page, request }) => {
  let slug = '';
  try {
    const created = await request.post(`${API}/projects`, {
      data: { title: `e2e khong nhap ${Date.now()}`, scene_count: 3 },
    });
    slug = (await created.json()).slug;
    const errors: string[] = [];
    page.on('response', (r) => {
      if (r.status() >= 400) errors.push(`${r.status()} ${r.url()}`);
    });
    await page.goto(`/p/${slug}`);
    const group = page.getByRole('group', { name: vi.nav.openProject });
    await expect(group.getByRole('link')).toHaveText([vi.nav.compose, vi.nav.audio, vi.nav.export]);
    expect(errors).toEqual([]);
  } finally {
    await deleteProject(request, slug);
  }
});
