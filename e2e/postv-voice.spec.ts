import { expect, test } from '@playwright/test';

import { vi } from '../frontend/src/i18n/vi';
import { API, deleteProject } from './helpers';

const T = vi.postv.voice;

/** Dự án PostV có bài, một bình luận và lời đọc ở mọi đoạn (chưa có giọng). */
async function createPostv(request: import('@playwright/test').APIRequestContext, title: string) {
  const created = await request.post(`${API}/projects`, { data: { title, kind: 'postv' } });
  expect(created.ok()).toBeTruthy();
  const project = await created.json();
  project.post = { ...project.post, handle: 'tac_gia', text: 'Hôm qua mình quên ví.' };
  project.comments = [{ id: 'c1', handle: 'user_b', text: 'Quán ở đâu vậy bạn?', picked: true }];
  project.segments = [
    { role: 'hook', card: 'hook', voice: 'Quên ví ở quán cà phê.', ref: null },
    { role: 'post', card: 'post', voice: 'Hôm qua mình quên ví.', ref: null },
    { role: 'comment', card: 'comment', voice: 'Quán ở đâu vậy bạn?', ref: 'c1' },
  ];
  const saved = await request.put(`${API}/projects/${project.slug}`, { data: project });
  expect(saved.ok()).toBeTruthy();
  return project.slug as string;
}

test('bước 3: sinh giọng VieNeu thật, mỗi người một giọng, nghe được trong app', async ({
  page,
  request,
}) => {
  const health = await (await request.get(`${API}/health`)).json();
  test.skip(!health.vieneu, 'Máy này chưa cài VieNeu (backend/.venv-tts)');
  test.setTimeout(240_000);
  let slug = '';
  try {
    slug = await createPostv(request, `E2E giọng ${Date.now()}`);
    await page.goto(`/postv/${slug}/script`);
    const card = page.getByRole('region', { name: T.title });
    // ba người đọc, giọng không trùng
    await expect(card.getByLabel(T.voiceOf(T.narrator))).toBeVisible({ timeout: 60_000 }); // lần đầu nạp danh sách giọng
    await expect(card.getByLabel(T.voiceOf('tac_gia'))).toBeVisible();
    await expect(card.getByLabel(T.voiceOf('user_b'))).toBeVisible();
    const picked = await card
      .locator('select')
      .evaluateAll((els) =>
        els.map((el) => (el as HTMLSelectElement).selectedOptions[0]!.textContent),
      );
    expect(new Set(picked).size).toBe(3);

    await card.getByRole('button', { name: T.synthesize, exact: true }).click();
    await expect(card.getByRole('progressbar', { name: T.progress })).toBeVisible();
    await expect(card.getByText(/^Đã sinh xong/)).toBeVisible({ timeout: 200_000 });
    await expect(card.getByLabel(T.listen)).toBeVisible();
    await expect(card.getByText(T.fresh)).toBeVisible();

    // thanh trái hiện VieNeu
    await expect(page.getByRole('list', { name: vi.nav.env })).toContainText('VieNeu: có');

    // đổi lời một đoạn: báo phải sinh lại
    const box = page.getByLabel(vi.postv.script.segmentLabel(2, vi.postv.pick.roles.post));
    await box.fill('Hôm qua mình để quên cái ví trên bàn.');
    await expect(card.getByText(T.stale)).toBeVisible({ timeout: 15_000 });
  } finally {
    await deleteProject(request, slug);
  }
});
