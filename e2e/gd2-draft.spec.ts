import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { expect, test } from '@playwright/test';

import { vi } from '../frontend/src/i18n/vi';
import { API, deleteProject } from './helpers';

const FIXTURE = join(process.cwd(), 'backend', 'tests', 'data', 'hbt-draft.sample.json');

test('Dán JSON nháp → Kiểm tra → Tạo dự án → mở trình soạn, có draft.json', async ({
  page,
  request,
}) => {
  test.setTimeout(60_000);
  const draft = readFileSync(FIXTURE, 'utf-8');
  const parsed = JSON.parse(draft) as {
    topic: string;
    scenes: { voice: string; image_prompt: string }[];
  };
  let slug = '';
  try {
    await page.goto('/');
    await page.getByRole('button', { name: vi.gd2.button, exact: true }).click();
    const dialog = page.getByRole('dialog', { name: vi.gd2.title });
    await dialog.getByLabel(vi.gd2.pasteLabel).fill(draft);
    await dialog.getByRole('button', { name: vi.gd2.check, exact: true }).click();
    await expect(dialog.getByText(vi.gd2.allGood)).toBeVisible();
    await expect(dialog.getByText(parsed.topic, { exact: true })).toBeVisible();
    await dialog.getByRole('button', { name: vi.gd2.create, exact: true }).click();

    await page.waitForURL(/\/p\/[^/]+$/);
    slug = new URL(page.url()).pathname.split('/').pop() ?? '';
    expect(slug).not.toBe('');

    const project = await (await request.get(`${API}/projects/${slug}`)).json();
    expect(project.title).toBe(parsed.topic);
    expect(project.scenes).toHaveLength(parsed.scenes.length);
    expect(project.scenes[1].voice).toBe(parsed.scenes[1].voice);
    const saved = await (await request.get(`${API}/projects/${slug}/draft`)).json();
    expect(saved.scenes[1].image_prompt).toBe(parsed.scenes[1].image_prompt);
    expect(saved.images_approved).toBe(false);
  } finally {
    await deleteProject(request, slug);
  }
});
