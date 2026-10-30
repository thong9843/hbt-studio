import { expect, test } from '@playwright/test';

import { vi } from '../frontend/src/i18n/vi';
import { API, deleteProject } from './helpers';

const SAMPLE_POST = `tac_gia
1 giờ
Hôm qua mình bỏ quên ví ở quán cà phê. May mà bạn nhân viên cất giữ hộ cẩn thận.
120 bình luận · 45 chia sẻ

user_b
40 phút
Quán ở đâu vậy bạn ơi?

user_c
20 phút
Người tốt việc tốt, thả tim nè!`;

const SCRIPT_JSON = JSON.stringify({
  postv_script: 1,
  style: 'ke-chuyen',
  hook: { text: 'Quên ví ở quán', accent: 'quên ví' },
  segments: [
    { role: 'hook', speaker: 'narrator', voice: 'Quên ví ở quán cà phê.', card: 'hook' },
    { role: 'post', speaker: 'post', voice: 'Hôm qua mình bỏ quên ví.', card: 'post' },
    {
      role: 'comment',
      ref: 'c1',
      speaker: 'narrator',
      voice: 'Có người hỏi ngay:',
      card: 'comment',
    },
    { role: 'comment', ref: 'c1', speaker: 'c1', voice: 'Quán ở đâu vậy bạn ơi?', card: 'comment' },
    { role: 'commentary', speaker: 'narrator', voice: 'Bạn thấy sao?', card: 'none' },
  ],
  cast: { narrator: 'Adam bựa' },
  publish: { hook: 'Quên ví', hashtags: ['chuyentute'] },
});

test('PVA: dán nguồn → chọn phong cách và bình luận → Tạo tự động (dừng ở pha 6 nếu thiếu VieNeu)', async ({
  page,
  request,
}) => {
  test.setTimeout(240_000);
  const title = `E2E PVA Auto ${Date.now()}`;
  let slug = '';
  try {
    const res = await request.post(`${API}/projects`, { data: { title, kind: 'postv' } });
    expect(res.ok()).toBeTruthy();
    slug = (await res.json()).slug;

    await page.goto(`/postv/${slug}`);
    const textarea = page.getByPlaceholder(vi.postv.source.pastePlaceholder);
    await textarea.fill(SAMPLE_POST);
    const splitBtn = page.getByRole('button', { name: vi.postv.source.split, exact: true });
    await expect(splitBtn).toBeEnabled();
    await splitBtn.click();
    await expect(page.getByText(/1 bài ·/)).toBeVisible({ timeout: 15_000 });

    const autoPanel = page.getByRole('region', { name: vi.postv.auto.title });
    await expect(autoPanel).toBeVisible();

    // Chọn phong cách Hài hước và số bình luận 2
    await autoPanel.getByRole('button', { name: 'Hài hước' }).click();
    await autoPanel.getByRole('button', { name: '2' }).click();

    // Kiểm tra trạng thái VieNeu qua API trước khi chạy
    const healthRes = await request.get(`${API}/health`);
    const health = await healthRes.json();
    const hasVieNeu = Boolean(health.vieneu);
    if (hasVieNeu) {
      test.setTimeout(600_000);
    }

    // Bấm Tạo tự động
    const startBtn = autoPanel.getByRole('button', { name: vi.postv.auto.submit });
    await expect(startBtn).toBeEnabled();
    await startBtn.click();

    // Tiến độ hiển thị
    await expect(autoPanel.getByRole('progressbar', { name: vi.postv.auto.title })).toBeVisible({
      timeout: 10_000,
    });

    const scriptBtn = page.getByRole('button', { name: vi.postv.auto.goToScript });
    const previewBtn = page.getByRole('button', { name: vi.postv.auto.goToPreview });

    if (hasVieNeu) {
      // Có VieNeu: BẮT BUỘC tới Xem nhanh và có video
      await expect(previewBtn).toBeVisible({ timeout: 540_000 });
      await previewBtn.click();
      await expect(page).toHaveURL(new RegExp(`/postv/${slug}/preview`));
      // Chờ video preview sẵn sàng (sau chuỗi 7 pha đã tạo Xem nhanh)
      const player = page.getByLabel(vi.postv.render.player);
      await expect(player.or(page.locator('video'))).toBeVisible({ timeout: 30_000 });
    } else {
      // Thiếu VieNeu: BẮT BUỘC dừng pha 6 (lỗi rõ), giữ kịch bản pha 1–5
      test.info().annotations.push({
        type: 'info',
        description: `Thiếu VieNeu: ${health.vieneu_note ?? 'chưa cài hoặc thiếu trọng số'}`,
      });
      await expect(scriptBtn).toBeVisible({ timeout: 180_000 });
      const project = await (await request.get(`${API}/projects/${slug}`)).json();
      expect(project.segments.length).toBeGreaterThan(0);
      expect(project.hook.text).toBeTruthy();
      await scriptBtn.click();
      await expect(page).toHaveURL(new RegExp(`/postv/${slug}/script`));
    }
  } finally {
    await page
      .evaluate(() => {
        document.querySelectorAll('video, audio').forEach((el) => {
          const m = el as HTMLMediaElement;
          m.pause();
          m.removeAttribute('src');
          m.load();
        });
      })
      .catch(() => {});
    await page.goto('about:blank').catch(() => {});
    await page.close().catch(() => {});
    await deleteProject(request, slug);
  }
});

test('PVA: Dán JSON kịch bản ở Bước 3 → Kiểm tra → Áp dụng thành công', async ({
  page,
  request,
}) => {
  test.setTimeout(90_000);
  const title = `E2E PVA JSON ${Date.now()}`;
  let slug = '';
  try {
    const res = await request.post(`${API}/projects`, { data: { title, kind: 'postv' } });
    expect(res.ok()).toBeTruthy();
    const proj = await res.json();
    slug = proj.slug;

    // Chuẩn bị comments c1
    proj.comments = [{ id: 'c1', handle: 'user_b', text: 'Quán ở đâu vậy?', picked: true }];
    await request.put(`${API}/projects/${slug}`, { data: proj });

    await page.goto(`/postv/${slug}/script`);
    const openBtn = page.getByRole('button', { name: vi.postv.scriptJson.button });
    await expect(openBtn).toBeVisible();
    await openBtn.click();

    const dialog = page.getByRole('dialog', { name: vi.postv.scriptJson.dialogTitle });
    await expect(dialog).toBeVisible();

    const jsonInput = dialog.getByLabel(vi.postv.scriptJson.dialogTitle);
    await jsonInput.fill(SCRIPT_JSON);

    const checkBtn = dialog.getByRole('button', { name: vi.postv.scriptJson.check });
    await checkBtn.click();

    await expect(dialog.getByText(vi.postv.scriptJson.valid)).toBeVisible({ timeout: 10_000 });

    const applyBtn = dialog.getByRole('button', { name: vi.postv.scriptJson.apply });
    await expect(applyBtn).toBeEnabled();
    await applyBtn.click();

    // Kiểm tra trên server dữ liệu đã cập nhật
    await expect(async () => {
      const updated = await (await request.get(`${API}/projects/${slug}`)).json();
      expect(updated.hook.text).toBe('Quên ví ở quán');
      expect(updated.segments).toHaveLength(5);
    }).toPass({ timeout: 15_000 });
  } finally {
    await page
      .evaluate(() => {
        document.querySelectorAll('video, audio').forEach((el) => {
          const m = el as HTMLMediaElement;
          m.pause();
          m.removeAttribute('src');
          m.load();
        });
      })
      .catch(() => {});
    await page.goto('about:blank').catch(() => {});
    await page.close().catch(() => {});
    await deleteProject(request, slug);
  }
});
