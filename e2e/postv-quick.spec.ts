import { expect, test } from '@playwright/test';
import { vi } from '../frontend/src/i18n/vi';

test('PV9: Dán link → thấy 6 bước tiến trình → thấy video hoàn thành → Chỉnh chi tiết', async ({
  page,
}) => {
  const T = vi.postvQuick;
  const mockSlug = 'test-pv9-quick';
  const mockJobId = 'job-pv9-123';

  // Giả lập API cho luồng nhanh
  await page.route('**/api/projects', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            slug: mockSlug,
            title: 'Video Threads Mẫu',
            kind: 'postv',
            updated_at: '2026-11-06T12:00:00',
            thumb: null,
            cover: null,
            last_render: null,
            last_final: null,
          },
        ]),
      });
      return;
    }
    await route.continue();
  });

  await page.route('**/api/voices', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        provider: 'vieneu',
        voices: [
          { id: 'adam-bua', label: 'Adam bựa', gender: 'Nam', region: 'Bắc', style: 'Tự nhiên' },
        ],
      }),
    });
  });

  await page.route('**/api/gd2/voice/preferences', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ voice_id: 'adam-bua' }),
    });
  });

  await page.route('**/api/jobs', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  await page.route('**/api/postv/auto', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        project_slug: mockSlug,
        job_id: mockJobId,
        existing_slug: null,
      }),
    });
  });

  await page.route(`**/api/jobs/${mockJobId}/events`, async (route) => {
    const sseBody = [
      'event: progress\n',
      `data: ${JSON.stringify({
        stage: 'fetch',
        status: 'done',
        progress: 15,
        message: 'Đã tải bài viết',
      })}\n\n`,
      'event: progress\n',
      `data: ${JSON.stringify({
        stage: 'pick',
        status: 'done',
        progress: 30,
        message: 'Đã chọn bình luận',
        data: {
          handle: 'tac_gia',
          snippet: 'Bài viết hay trên Threads',
          picked_count: 2,
          total_comments: 4,
        },
      })}\n\n`,
      'event: progress\n',
      `data: ${JSON.stringify({
        stage: 'script',
        status: 'done',
        progress: 45,
        message: 'Kịch bản xong',
      })}\n\n`,
      'event: progress\n',
      `data: ${JSON.stringify({
        stage: 'voice',
        status: 'done',
        progress: 65,
        message: 'Sinh giọng xong',
      })}\n\n`,
      'event: progress\n',
      `data: ${JSON.stringify({
        stage: 'render',
        status: 'done',
        progress: 95,
        message: 'Dựng xong',
      })}\n\n`,
      'event: end\n',
      `data: ${JSON.stringify({
        status: 'done',
        output: {
          video: 'renders/job-1/video.mp4',
          cover: 'renders/job-1/cover.jpg',
          publish: 'renders/job-1/publish.txt',
          duration: 65.0,
          fps: 60,
          project_slug: mockSlug,
        },
      })}\n\n`,
    ].join('');

    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      headers: {
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive',
      },
      body: sseBody,
    });
  });

  // Mở trang /postv
  await page.goto('/postv');

  // Kiểm tra lời chào và ô nhập liệu
  await expect(page.getByText(T.greeting)).toBeVisible();
  const textarea = page.getByPlaceholder(T.inputPlaceholder);
  await expect(textarea).toBeVisible();

  // Dán link Threads
  await textarea.fill('https://www.threads.net/@tac_gia/post/test123');

  // Bấm Tạo video
  const createBtn = page.getByRole('button', { name: T.createBtn });
  await expect(createBtn).toBeEnabled();
  await createBtn.click();

  // Thấy tiến trình 6 bước
  await expect(page.getByText(T.stages.fetch)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(T.stages.pick)).toBeVisible();
  await expect(page.getByText(T.stages.script)).toBeVisible();
  await expect(page.getByText(T.stages.voice)).toBeVisible();
  await expect(page.getByText(T.stages.render)).toBeVisible();
  await expect(page.getByText(T.stages.done)).toBeVisible();

  // Thấy thẻ kết quả video đã hoàn thành
  await expect(page.getByText(T.result.title)).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole('link', { name: T.result.downloadVideo })).toBeVisible();
  await expect(page.getByRole('button', { name: T.result.copyPublish })).toBeVisible();

  // Bấm "Chỉnh chi tiết" mở đúng dự án
  const editDetailsLink = page.getByRole('link', { name: T.result.editDetails });
  await expect(editDetailsLink).toBeVisible();
  await editDetailsLink.click();

  await expect(page).toHaveURL(new RegExp(`/postv/${mockSlug}/export`));
});
