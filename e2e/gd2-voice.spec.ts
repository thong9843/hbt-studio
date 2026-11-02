import { expect, test } from '@playwright/test';

import { vi } from '../frontend/src/i18n/vi';
import { API, deleteProject } from './helpers';

const T = vi.gd2.voice;

test('Âm thanh: thẻ Giọng VieNeu luôn có mặt; có VieNeu thì sinh giọng thật và nhớ giọng đã chọn', async ({
  page,
  request,
}) => {
  test.setTimeout(300_000);
  const health = await (await request.get(`${API}/health`)).json();
  let slug = '';
  let remembered: string | null = null;
  try {
    const created = await request.post(`${API}/projects`, {
      data: { title: `e2e giọng hbt ${Date.now()}`, scene_count: 3 },
    });
    expect(created.ok()).toBeTruthy();
    const project = await created.json();
    slug = project.slug;
    const lines = [
      'Muỗi đánh hơi khí CO2 từ xa khoảng 10{mười} mét.',
      'Thở nhiều, | dễ bị đốt.',
      '',
    ];
    project.scenes.forEach((s: { voice: string }, i: number) => (s.voice = lines[i]));
    expect((await request.put(`${API}/projects/${slug}`, { data: project })).ok()).toBeTruthy();
    remembered = (await (await request.get(`${API}/gd2/voice/preferences`)).json()).voice_id;

    await page.goto(`/p/${slug}/audio`);
    const card = page.getByRole('region', { name: T.title });
    await expect(card).toBeVisible(); // không ẩn, kể cả khi chưa cài VieNeu
    if (!health.vieneu) {
      await expect(card.getByText(T.unavailableTitle)).toBeVisible();
      await expect(card.getByText(T.unavailableLead)).toBeVisible();
      return;
    }

    // Có VieNeu: chọn giọng, tạo giọng thật, nghe được trong app.
    const pick = card.getByLabel(T.pick);
    await expect(pick).toBeEnabled({ timeout: 90_000 }); // lần đầu nạp danh sách giọng
    const first = await pick.locator('option:not([value=""])').first().getAttribute('value');
    await pick.selectOption(first as string);
    await card.getByRole('button', { name: T.synthesize, exact: true }).click();
    await expect(card.getByRole('progressbar', { name: T.progress })).toBeVisible();
    await expect(card.locator('audio')).toBeVisible({ timeout: 240_000 });
    const saved = await (await request.get(`${API}/projects/${slug}`)).json();
    expect(saved.voice).toBe('voice.wav');

    // Mở lại: giọng đã chọn được nhớ.
    await page.reload();
    await expect(page.getByRole('region', { name: T.title }).getByLabel(T.pick)).toHaveValue(
      first as string,
      { timeout: 90_000 },
    );
  } finally {
    await request.put(`${API}/gd2/voice/preferences`, { data: { voice_id: remembered } });
    await deleteProject(request, slug);
  }
});
