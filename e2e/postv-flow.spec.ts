import { execFileSync } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { expect, test } from '@playwright/test';

import { vi } from '../frontend/src/i18n/vi';
import { API, deleteProject } from './helpers';

/** Giọng giả ngắn bằng ffmpeg để test mà không cần model TTS/Whisper. */
function makeVoice(dir: string): string {
  const file = join(dir, 'voice.wav');
  execFileSync('ffmpeg', [
    '-v',
    'error',
    '-y',
    '-f',
    'lavfi',
    '-i',
    "aevalsrc='if(gt(t,0.2)*lt(mod(t-0.2,1.5),0.8),0.3*sin(2*PI*400*t),0)':d=4:s=44100",
    file,
  ]);
  return file;
}

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

test('luồng PostV đủ 5 bước: dán nguồn → chọn đoạn → nạp file giọng → xem trước tĩnh & bíp → xuất video', async ({
  page,
  request,
}) => {
  test.setTimeout(120_000);
  const dir = mkdtempSync(join(tmpdir(), 'hbt-postv-flow-'));
  const voiceFile = makeVoice(dir);
  const title = `E2E Luồng đủ ${Date.now()}`;
  let slug = '';

  try {
    // 1. Tạo dự án PostV
    const res = await request.post(`${API}/projects`, { data: { title, kind: 'postv' } });
    expect(res.ok()).toBeTruthy();
    slug = (await res.json()).slug;

    // --- BƯỚC 1: Nguồn ---
    await page.goto(`/postv/${slug}`);
    await expect(page.getByRole('heading', { name: title })).toBeVisible();

    // Dán nội dung và bấm Tách bài
    const textarea = page.getByPlaceholder(vi.postv.source.pastePlaceholder);
    await textarea.fill(SAMPLE_POST);
    const splitBtn = page.getByRole('button', { name: vi.postv.source.split, exact: true });
    await expect(splitBtn).toBeEnabled();
    await splitBtn.click();

    // Kết quả tách bài
    await expect(page.getByText(/1 bài ·/)).toBeVisible({ timeout: 15_000 });

    // Tiếp sang Bước 2
    const toPick = page.getByRole('button', { name: vi.postv.next.pick });
    await expect(toPick).toBeEnabled({ timeout: 15_000 });
    await toPick.click();

    // --- BƯỚC 2: Chọn đoạn ---
    await expect(page).toHaveURL(new RegExp(`/postv/${slug}/pick`));
    await expect(page.getByRole('heading', { name: vi.postv.pick.listTitle })).toBeVisible();

    // Chọn tiếp sang Bước 3
    const toScript = page.getByRole('button', { name: vi.postv.next.script });
    await expect(toScript).toBeEnabled({ timeout: 15_000 });
    await toScript.click();

    // --- BƯỚC 3: Kịch bản & giọng ---
    await expect(page).toHaveURL(new RegExp(`/postv/${slug}/script`));
    await expect(page.getByRole('region', { name: vi.postv.voice.title })).toBeVisible();

    // Chuyển sang chế độ "Nhập file"
    await page.getByRole('button', { name: vi.postv.voice.file, exact: true }).click();

    // Nạp file giọng bằng input file của AudioDrop
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles(voiceFile);
    await expect(page.getByLabel(vi.postv.voice.listen)).toBeVisible({ timeout: 15_000 });

    // Tiếp sang Bước 4: Xem trước
    const toPreview = page.getByRole('button', { name: vi.postv.script.next });
    await expect(toPreview).toBeEnabled();
    await toPreview.click();

    // --- BƯỚC 4: Xem trước ---
    await expect(page).toHaveURL(new RegExp(`/postv/${slug}/preview`));
    await expect(page.getByRole('heading', { name: vi.postv.preview.cards })).toBeVisible();

    // Thấy nút nghe thử bíp và bấm thử
    const bleepBtn = page.getByRole('button', { name: vi.postv.preview.testBleep });
    await expect(bleepBtn).toBeVisible();
    await bleepBtn.click();

    // Thấy các nút chuyển chế độ xem trước (Toàn khung 9:16 / Chỉ thẻ bài)
    await expect(page.getByRole('button', { name: vi.postv.preview.viewStatic })).toBeVisible();
    await expect(page.getByRole('button', { name: vi.postv.preview.viewCard })).toBeVisible();

    // Bấm Xem nhanh thật (giọng nhập file), chờ có video (sửa lệch PV6)
    const quick = page.getByRole('button', { name: vi.postv.preview.quick, exact: true });
    await expect(quick).toBeEnabled({ timeout: 30_000 });
    await quick.click();
    const aside = page.getByRole('complementary', { name: vi.postv.preview.previewOf });
    await expect(aside.getByRole('progressbar', { name: vi.postv.render.progress })).toBeVisible();
    const player = page.getByLabel(vi.postv.render.player);
    await expect(player).toBeVisible({ timeout: 150_000 });
    const src = await player.getAttribute('src');
    expect(src).toBeTruthy();

    // Sang Bước 5: Xuất qua thanh 5 bước hoặc thanh điều hướng bên trái
    const toExport = page.getByRole('link', { name: new RegExp(`.*${vi.postv.steps[4]}$`) });
    await toExport.first().click();

    // --- BƯỚC 5: Xuất ---
    await expect(page).toHaveURL(new RegExp(`/postv/${slug}/export`));
    await expect(page.getByRole('heading', { name: vi.postv.export.title })).toBeVisible();

    // Thấy các tùy chọn fps
    await expect(page.getByRole('button', { name: '30 fps' })).toBeVisible();
    await expect(page.getByRole('button', { name: '50 fps' })).toBeVisible();
    await expect(page.getByRole('button', { name: '60 fps' })).toBeVisible();

    // Xuất bản đẹp 30 fps chỉ chạy khi có nền (tự bỏ qua kèm lý do)
    const clips = await (await request.get(`${API}/backgrounds`)).json();
    if (clips.length > 0) {
      await page.getByRole('button', { name: '30 fps' }).click();
      const exportBtn = page.getByRole('button', { name: vi.postv.export.final(30), exact: true });
      await expect(exportBtn).toBeEnabled({ timeout: 30_000 });
      await exportBtn.click();
      await expect(
        page.getByRole('progressbar', { name: vi.postv.render.progress }).first(),
      ).toBeVisible();
      const finalPlayer = page.getByLabel(vi.postv.render.player);
      await expect(finalPlayer).toBeVisible({ timeout: 180_000 });
    } else {
      test.info().annotations.push({
        type: 'skip-export',
        description: 'Tự bỏ qua Xuất bản đẹp vì thư viện nền trống (library/backgrounds)',
      });
    }

    // Thấy phần Ảnh bìa, bật ảnh bìa và thấy chip "Khung gameplay" / "Ảnh tải lên"
    await expect(page.getByRole('heading', { name: vi.postv.export.cover })).toBeVisible();
    const addCoverBtn = page.getByRole('button', { name: vi.export.thumb.add });
    await expect(addCoverBtn).toBeVisible();
    await addCoverBtn.click();
    await expect(page.getByRole('button', { name: vi.postv.export.gameplayFrame })).toBeVisible();
    await expect(page.getByRole('button', { name: vi.postv.export.customUpload })).toBeVisible();

    // Thấy phần Nội dung đăng
    await expect(page.getByRole('heading', { name: vi.postv.export.publishContent })).toBeVisible();
    await expect(page.getByRole('button', { name: /Sao chép/ }).first()).toBeVisible();

    // Thấy phần Lịch sử lần xuất và nút Dọn file tạm
    await expect(page.getByRole('heading', { name: vi.export.history.title })).toBeVisible();
    const cleanBtn = page.getByRole('button', { name: vi.postv.export.cleanBuild });
    await expect(cleanBtn).toBeVisible();
    await cleanBtn.click();
    await expect(page.getByText(vi.postv.export.cleanDone)).toBeVisible({ timeout: 10_000 });
  } finally {
    rmSync(dir, { recursive: true, force: true });
    await page.goto('about:blank').catch(() => {});
    await deleteProject(request, slug);
  }
});
