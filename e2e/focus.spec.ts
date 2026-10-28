import { expect, test, type Locator, type Page } from '@playwright/test';

import { vi } from '../frontend/src/i18n/vi';

const API = 'http://127.0.0.1:8000/api';

/** Nhấn Tab `times` lần; sau mỗi lần phần tử đang focus phải nằm trong `root`. */
async function tabStaysInside(page: Page, root: Locator, times: number) {
  for (let i = 0; i < times; i++) {
    await page.keyboard.press(i % 3 === 2 ? 'Shift+Tab' : 'Tab');
    const inside = await root.evaluate((el) => el.contains(document.activeElement));
    expect(inside, `Tab lần ${i + 1} ra khỏi vùng`).toBe(true);
  }
}

test('Tab/focus: thanh trái đúng thứ tự; Dialog và Menu giữ focus; Esc trả focus về nút đã mở', async ({
  page,
  request,
}) => {
  let slug = '';
  try {
    // 1. Tab qua thanh trái, đúng thứ tự trên trang chủ.
    await page.goto('/');
    await expect(page.getByRole('navigation', { name: vi.nav.main })).toBeVisible();
    const order = [
      page.getByRole('link', { name: vi.appName, exact: true }),
      page.getByRole('button', { name: vi.nav.newVideo, exact: true }),
      page.getByRole('link', { name: vi.nav.home, exact: true }),
      page.getByRole('link', { name: vi.nav.projects, exact: true }),
      page.getByRole('link', { name: vi.nav.settings, exact: true }),
      page.getByRole('button', { name: /^Đổi sang chế độ/ }),
    ];
    for (const stop of order) {
      await page.keyboard.press('Tab');
      await expect(stop).toBeFocused();
    }
    // Có vòng focus nhìn thấy (focus-visible) trên mục đang chọn bằng bàn phím.
    const outline = await order[5].evaluate((el) => getComputedStyle(el).outlineStyle);
    expect(outline).not.toBe('none');

    // 2. Dialog: Tab/Shift+Tab không ra ngoài; Esc đóng và trả focus về nút "Tạo video".
    const newVideo = page.getByRole('button', { name: vi.nav.newVideo, exact: true });
    await newVideo.focus();
    await page.keyboard.press('Enter');
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await tabStaysInside(page, dialog, 12);
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
    await expect(newVideo).toBeFocused();

    // 3. Menu ⋯ ở thanh đầu Soạn video: focus nằm trong menu; Esc trả về nút ⋯.
    const created = await request.post(`${API}/projects`, {
      data: { title: `e2e focus ${Date.now()}`, scene_count: 3 },
    });
    expect(created.ok()).toBeTruthy();
    slug = (await created.json()).slug;
    await page.goto(`/p/${slug}`);
    const more = page.getByRole('button', { name: vi.script.menu, exact: true });
    await more.focus();
    await page.keyboard.press('Enter');
    const menu = page.getByRole('menu');
    await expect(menu).toBeVisible();
    await tabStaysInside(page, menu, 6);
    await page.keyboard.press('Escape');
    await expect(menu).toBeHidden();
    await expect(more).toBeFocused();

    // 4. Menu → Bản sao lưu (Dialog): giữ focus trong hộp; Esc trả focus về nút ⋯.
    await page.keyboard.press('Enter');
    await page.getByRole('menuitem', { name: vi.script.backups.menu }).click();
    const backups = page.getByRole('dialog');
    await expect(backups).toBeVisible();
    await tabStaysInside(page, backups, 6);
    await page.keyboard.press('Escape');
    await expect(backups).toBeHidden();
    await expect(more).toBeFocused();
  } finally {
    if (slug) await request.delete(`${API}/projects/${slug}`);
  }
});
