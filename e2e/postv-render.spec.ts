import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { expect, test, type APIRequestContext } from '@playwright/test';

import { vi } from '../frontend/src/i18n/vi';
import { API, deleteProject } from './helpers';

const R = vi.postv.render;

/** Giọng giả 3 câu (1 s tiếng, 0,8 s lặng) bằng ffmpeg: căn bằng khoảng lặng, không cần Whisper. */
function makeVoice(dir: string): string {
  const file = join(dir, 'voice.wav');
  execFileSync('ffmpeg', [
    '-v',
    'error',
    '-y',
    '-f',
    'lavfi',
    '-i',
    "aevalsrc='if(gt(t,0.3)*lt(mod(t-0.3,1.8),1),0.4*sin(2*PI*300*t),0)':d=5.2:s=44100",
    file,
  ]);
  return file;
}

/** Dự án PostV có bài, một bình luận, ba đoạn lời và file giọng; căn bằng khoảng lặng. */
async function createPostv(request: APIRequestContext, title: string, voicePath: string) {
  const created = await request.post(`${API}/projects`, { data: { title, kind: 'postv' } });
  expect(created.ok()).toBeTruthy();
  const project = await created.json();
  project.post = {
    ...project.post,
    handle: 'tac_gia',
    text: 'Hôm qua mình quên ví.',
    likes: 1200,
    replies: 34,
    shares: 56,
  };
  project.comments = [{ id: 'c1', handle: 'user_b', text: 'Quán ở đâu vậy bạn?', picked: true }];
  project.segments = [
    { role: 'hook', card: 'hook', voice: 'Quên ví ở quán cà phê.', ref: null },
    { role: 'post', card: 'post', voice: 'Hôm qua mình quên ví.', ref: null },
    { role: 'comment', card: 'comment', voice: 'Quán ở đâu vậy bạn?', ref: 'c1' },
  ];
  project.settings = { ...project.settings, aligner: 'silence', outro: false };
  const saved = await request.put(`${API}/projects/${project.slug}`, { data: project });
  expect(saved.ok()).toBeTruthy();
  const upload = await request.post(`${API}/projects/${project.slug}/assets`, {
    multipart: {
      kind: 'voice',
      file: { name: 'voice.wav', mimeType: 'audio/wav', buffer: readFileSync(voicePath) },
    },
  });
  expect(upload.ok(), await upload.text()).toBeTruthy();
  return project.slug as string;
}

test('bước 4: Xem nhanh dựng video PostV thật và phát được trong app', async ({
  page,
  request,
}) => {
  const clips = await (await request.get(`${API}/backgrounds`)).json();
  test.skip(clips.length === 0, 'Thư viện nền chưa có clip nào (library/backgrounds)');
  test.setTimeout(180_000);
  const dir = mkdtempSync(join(tmpdir(), 'hbt-e2e-'));
  let slug = '';
  try {
    slug = await createPostv(request, `E2E dựng ${Date.now()}`, makeVoice(dir));
    await page.goto(`/postv/${slug}/preview`);
    const quick = page.getByRole('button', { name: vi.postv.preview.quick, exact: true });
    await expect(quick).toBeEnabled({ timeout: 30_000 });
    await quick.click();
    const aside = page.getByRole('complementary', { name: vi.postv.preview.previewOf });
    await expect(aside.getByRole('progressbar', { name: R.progress })).toBeVisible();
    const player = page.getByLabel(R.player);
    await expect(player).toBeVisible({ timeout: 150_000 });
    await expect(page.getByRole('link', { name: R.video })).toBeVisible();
    const src = await player.getAttribute('src');
    const video = await request.get(src ?? '');
    expect(video.ok()).toBeTruthy();
    expect((await video.body()).length).toBeGreaterThan(10_000);
  } finally {
    rmSync(dir, { recursive: true, force: true });
    await deleteProject(request, slug);
  }
});
