import { expect, test } from '@playwright/test';

import { vi } from '../frontend/src/i18n/vi';
import { API, createRenderableProject, deleteProject } from './helpers';

test('Xem nhanh từ Soạn video tự dựng ở tab Xuất; thẻ trái hiện tiến độ và Huỷ dừng job', async ({
  page,
  request,
}) => {
  test.setTimeout(120_000);
  let slug = '';
  try {
    slug = await createRenderableProject(request, `E2E xuất ${Date.now()}`);

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
    await deleteProject(request, slug);
  }
});

test('Lịch sử: dựng Xem nhanh xong → menu ⋯ của lần xuất → Xoá → xác nhận → thẻ biến mất', async ({
  page,
  request,
}) => {
  test.setTimeout(240_000);
  let slug = '';
  try {
    slug = await createRenderableProject(request, `E2E xoá lần xuất ${Date.now()}`);
    await page.goto(`/p/${slug}/export`);
    const fast = page.getByRole('button', { name: vi.export.fast, exact: true });
    await expect(fast).toBeEnabled();
    await fast.click();

    // File giọng mẫu có đuôi thừa dài: xác nhận cắt (bước nghe lại) rồi dựng tiếp.
    await page
      .getByRole('button', { name: vi.export.confirmTrimButton, exact: true })
      .click({ timeout: 120_000 });

    // Dựng xong thì thẻ lịch sử xuất hiện với menu ⋯ của nó.
    const menu = page.getByRole('button', { name: /^Thao tác:/ });
    await expect(menu).toHaveCount(1, { timeout: 200_000 });
    const before = await (await request.get(`${API}/projects/${slug}/renders`)).json();
    expect(before).toHaveLength(1);

    // Chờ làm mới lịch sử/dự án sau khi dựng xong rồi mới thao tác (tránh bấm giữa lúc vẽ lại).
    await expect(page.getByText(vi.export.done, { exact: true }).first()).toBeVisible();
    await page.waitForLoadState('networkidle');

    await menu.click();
    await page.getByRole('menuitem', { name: vi.export.history.remove, exact: true }).click();
    const dialog = page.getByRole('alertdialog', { name: vi.export.history.deleteTitle });
    await expect(dialog).toBeVisible();
    await dialog.getByRole('button', { name: vi.export.history.remove, exact: true }).click();

    await expect(page.getByText(vi.export.history.deleted, { exact: true })).toBeVisible();
    await expect(menu).toHaveCount(0);
    const after = await (await request.get(`${API}/projects/${slug}/renders`)).json();
    expect(after).toHaveLength(0);
  } finally {
    await deleteProject(request, slug);
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
