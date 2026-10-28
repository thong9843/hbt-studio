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
    const add = scenes.getByRole('button', { name: vi.compose.scenes.add });
    for (let i = 0; i < 3; i++) await add.click();
    await expect(scenes.getByText(/^Cảnh \d+$/)).toHaveCount(6);

    await scenes.getByRole('button', { name: /^Cảnh 1/ }).click();
    await page.getByLabel(vi.compose.editor.voice).fill('Muỗi đốt người');
    await page.keyboard.press('Control+s');
    await expect(page.getByText(vi.compose.saveStatus.saved)).toBeVisible();

    await page.reload();
    await expect(scenes.getByText(/^Cảnh \d+$/)).toHaveCount(6);
    await expect(page.getByLabel(vi.compose.editor.voice)).toHaveValue('Muỗi đốt người');

    const saved = await (await request.get(`${API}/projects/${slug}`)).json();
    expect(saved.title).toBe(title);
    expect(saved.scenes).toHaveLength(6);
  } finally {
    if (slug) await request.delete(`${API}/projects/${slug}`);
  }
});
