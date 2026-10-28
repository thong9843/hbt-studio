import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { expect, test } from '@playwright/test';

import { vi } from '../frontend/src/i18n/vi';
import { deleteProject } from './helpers';

const API = 'http://127.0.0.1:8000/api';
const FIXTURE = join(process.cwd(), 'backend', 'tests', 'data', 'dao-phuc-sinh.cards.json');

test('Dán JSON dao-phuc-sinh → Áp dụng → tải lại còn dữ liệu → Khôi phục bản trước', async ({
  page,
  request,
}) => {
  test.setTimeout(90_000);
  const script = readFileSync(FIXTURE, 'utf-8');
  const cards = JSON.parse(script) as { card: { lines: { text: string }[] } }[];
  const firstText = cards[0].card.lines[0].text;
  let slug = '';
  try {
    const created = await request.post(`${API}/projects`, {
      data: { title: `e2e dán json ${Date.now()}`, scene_count: cards.length },
    });
    expect(created.ok()).toBeTruthy();
    const before = await created.json();
    slug = before.slug;
    expect(slug.startsWith('e2e-')).toBeTruthy();
    const beforeText: string = before.scenes[0].card.lines[0]?.text ?? '';
    expect(beforeText).not.toBe(firstText);

    // Dán → Kiểm tra → Áp dụng.
    await page.goto(`/p/${slug}`);
    await page.getByRole('button', { name: vi.script.open, exact: true }).click();
    const dialog = page.getByRole('dialog', { name: vi.script.title });
    await dialog.getByLabel(vi.script.pasteLabel).fill(script);
    await dialog.getByRole('button', { name: vi.script.check, exact: true }).click();
    await expect(dialog.getByText(vi.script.scenesEqual(cards.length, cards.length))).toBeVisible();
    await dialog.getByRole('button', { name: vi.script.applyN(cards.length), exact: true }).click();
    await expect(page.getByText(vi.script.applied(cards.length))).toBeVisible();
    await expect(dialog).toBeHidden();

    // Tải lại: dữ liệu còn trên đĩa và hiện ở ô chữ cảnh 1.
    const applied = await (await request.get(`${API}/projects/${slug}`)).json();
    expect(applied.scenes[0].card.lines[0].text).toBe(firstText);
    await page.reload();
    await expect(page.getByLabel(vi.compose.card.lineText(1), { exact: true })).toHaveValue(
      firstText,
    );

    // Khôi phục bản sao lưu lúc trước khi áp.
    await page.getByRole('button', { name: vi.script.menu, exact: true }).click();
    await page.getByRole('menuitem', { name: vi.script.backups.menu }).click();
    const list = page.getByRole('dialog', { name: vi.script.backups.title });
    await expect(list.getByText(vi.script.backups.reason.apply)).toBeVisible();
    await list.getByRole('button', { name: vi.script.backups.restore }).first().click();
    const confirm = page.getByRole('alertdialog', { name: vi.script.backups.confirmTitle });
    await confirm.getByRole('button', { name: vi.script.backups.restore }).click();
    await expect(page.getByText(vi.script.backups.done)).toBeVisible();

    const restored = await (await request.get(`${API}/projects/${slug}`)).json();
    expect(restored.scenes[0].card.lines[0]?.text ?? '').toBe(beforeText);
    await page.reload();
    await expect(page.getByLabel(vi.compose.meta.title, { exact: true })).toBeVisible();
    const line1 = page.getByLabel(vi.compose.card.lineText(1), { exact: true });
    if (beforeText) await expect(line1).toHaveValue(beforeText);
    else await expect(line1).toHaveCount(0); // dự án mới chưa có dòng chữ nào
  } finally {
    await deleteProject(request, slug);
  }
});
