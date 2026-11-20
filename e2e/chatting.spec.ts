import { expect, test } from '@playwright/test';
import { API } from './helpers';

test.describe('Chatting e2e flows (CH3)', () => {
  test('Ca 1: Dán chữ → Tạo video tự động qua 4 pha → mở trình soạn', async ({ page, request }) => {
    test.setTimeout(240_000);

    // Vào trang /chatting
    await page.goto('/chatting');
    await expect(page.locator('h1')).toContainText('Chatting');

    // Dán câu chuyện mẫu
    const textarea = page.locator('textarea');
    await textarea.fill(
      'Người yêu cũ nhắn lúc 2h sáng\nHôm qua bất ngờ nhận được tin nhắn hỏi thăm sau 3 năm chia tay. Câu chuyện dở khóc dở cười.',
    );

    // Bấm Tạo video
    const createBtn = page.locator('main').getByRole('button', { name: 'Tạo video' });
    await expect(createBtn).toBeEnabled();
    await createBtn.click();

    // Thấy thanh tiến độ xuất hiện
    await expect(page.locator('text=1. Lấy bài')).toBeVisible({ timeout: 15_000 });

    // Đợi chuỗi tự động hoàn tất và tự chuyển hướng sang /chatting/:slug
    await page.waitForURL(/\/chatting\/[a-z0-9-]+/, { timeout: 180_000 });

    // Kiểm tra đã vào màn biên tập và có danh sách tin nhắn
    await expect(page.locator('text=Nhân vật')).toBeVisible();
    await expect(page.locator('text=Danh sách tin nhắn')).toBeVisible();
    await expect(page.locator('text=Xem trước')).toBeVisible();
  });

  test('Ca 2: Sửa tin nhắn → Dựng Xem nhanh lại thành công', async ({ page, request }) => {
    test.setTimeout(240_000);

    // Tạo dự án nhanh qua API
    const res = await request.post(`${API}/chatting`, {
      data: {
        input: 'Chuyện vui bạn bè\nHôm nay đi ăn phở gặp lại bạn cũ.',
        platform: 'messenger',
        background: 'minecraft4-1080p60',
      },
    });
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    const slug = data.slug;
    const jobId = data.job_id;

    // Đợi job tạo dự án ban đầu hoàn tất trước khi mở màn soạn để tránh 409 bận
    for (let i = 0; i < 180; i++) {
      const jobRes = await request.get(`${API}/jobs/${jobId}`);
      if (jobRes.ok()) {
        const j = await jobRes.json();
        if (j.finished) break;
      }
      await page.waitForTimeout(1000);
    }

    // Vào màn chỉnh sửa của dự án
    await page.goto(`/chatting/${slug}`);
    await expect(page.locator('text=Nhân vật')).toBeVisible({ timeout: 30_000 });

    // Sửa nội dung tin nhắn đầu tiên
    const textarea = page.locator('main textarea');
    await textarea.fill('Alo bạn ơi tối nay rảnh không đi ăn ốc?');

    // Bấm nút Xem nhanh
    const previewBtn = page.getByRole('button', { name: 'Xem nhanh' });
    await expect(previewBtn).toBeEnabled();
    await previewBtn.click();

    // Thấy thông báo tiến độ dựng
    await expect(page.locator('text=Đang dựng video...')).toBeVisible({ timeout: 10_000 });

    // Đợi dựng hoàn tất
    await expect(page.locator('text=Dựng video hoàn tất!')).toBeVisible({ timeout: 120_000 });

    // Dọn dẹp dự án thử nghiệm
    await request.delete(`${API}/chatting/${slug}`).catch(() => {});
  });
});
