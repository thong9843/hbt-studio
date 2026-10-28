import { expect, test } from '@playwright/test';

import { vi } from '../frontend/src/i18n/vi';

const API = 'http://127.0.0.1:8000/api';

test('tạo project, thêm 3 cảnh, lưu, tải lại vẫn đủ dữ liệu', async ({ page, request }) => {
  const title = `E2E ${Date.now()}`;
  let slug = '';
  try {
    await page.goto('/projects');
    await page.getByRole('button', { name: vi.projects.create }).first().click();
    await page.getByLabel(vi.projects.dialog.name).fill(title);
    await page
      .getByRole('group', { name: vi.projects.dialog.scenes })
      .getByRole('button', { name: '3', exact: true })
      .click();
    await page.getByRole('button', { name: vi.projects.dialog.submit, exact: true }).click();
    await page.waitForURL(/\/p\/[^/]+$/);
    slug = new URL(page.url()).pathname.split('/')[2]!;

    const scenes = page.getByRole('region', { name: vi.compose.scenes.title });
    const sceneButtons = scenes.getByRole('button', { name: /^Cảnh \d+/ });
    const add = scenes.getByRole('button', { name: vi.compose.strip.add, exact: true });
    for (let i = 0; i < 3; i++) await add.click();
    await expect(sceneButtons).toHaveCount(6);

    // Sửa một cảnh: lời đọc + một dòng thẻ chữ.
    await sceneButtons.first().click();
    await page.getByLabel(vi.compose.voice.label).fill('Muỗi đốt người');
    await page.getByRole('button', { name: vi.compose.card.addLine, exact: true }).click();
    await page.getByLabel(vi.compose.card.lineText(1)).fill('MUỖI ĐỐT');
    await page.keyboard.press('Control+s');
    await expect(page.getByText(vi.compose.saveStatus.saved)).toBeVisible();

    // Tải lại trang: dữ liệu còn.
    await page.reload();
    await expect(sceneButtons).toHaveCount(6);
    await expect(page.getByLabel(vi.compose.voice.label)).toHaveValue('Muỗi đốt người');
    await expect(page.getByLabel(vi.compose.card.lineText(1))).toHaveValue('MUỖI ĐỐT');

    const saved = await (await request.get(`${API}/projects/${slug}`)).json();
    expect(saved.title).toBe(title);
    expect(saved.scenes).toHaveLength(6);
    expect(saved.scenes[0].voice).toBe('Muỗi đốt người');
    expect(saved.scenes[0].card.lines[0].text).toBe('MUỖI ĐỐT');
  } finally {
    if (slug) await request.delete(`${API}/projects/${slug}`);
  }
});
