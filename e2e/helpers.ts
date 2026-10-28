import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { expect, type APIRequestContext } from '@playwright/test';

export const API = 'http://127.0.0.1:8000/api';
export const SAMPLE = join(process.cwd(), 'workspace', 'samples', 'muoi');

/**
 * Xoá dự án thử bằng DELETE. Job vừa huỷ có thể còn giữ file nên máy chủ trả 409:
 * thử lại tới 20 lần (mỗi lần 500 ms); cuối cùng phải là 204.
 */
export async function deleteProject(request: APIRequestContext, slug: string): Promise<void> {
  if (!slug) return;
  let status = 0;
  for (let i = 0; i < 20; i++) {
    status = (await request.delete(`${API}/projects/${slug}`)).status();
    if (status !== 409) break;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  expect(status, `DELETE /projects/${slug}`).toBe(204);
}

/** Tạo dự án `scenes` cảnh có ảnh mẫu + giọng mẫu của "muỗi" và lời đọc ở mọi cảnh. */
export async function createRenderableProject(
  request: APIRequestContext,
  title: string,
  scenes = 3,
): Promise<string> {
  const created = await request.post(`${API}/projects`, {
    data: { title, scene_count: scenes },
  });
  expect(created.ok()).toBeTruthy();
  const slug: string = (await created.json()).slug;
  for (let i = 0; i < scenes; i++) {
    const res = await request.post(`${API}/projects/${slug}/assets`, {
      multipart: {
        kind: 'image',
        scene_index: String(i),
        file: {
          name: `scene-0${i + 1}.png`,
          mimeType: 'image/png',
          buffer: readFileSync(join(SAMPLE, 'images', `scene-0${i + 1}.png`)),
        },
      },
    });
    expect(res.ok()).toBeTruthy();
  }
  const voice = await request.post(`${API}/projects/${slug}/assets`, {
    multipart: {
      kind: 'voice',
      file: {
        name: 'voice.mp3',
        mimeType: 'audio/mpeg',
        buffer: readFileSync(join(SAMPLE, 'voice.mp3')),
      },
    },
  });
  expect(voice.ok()).toBeTruthy();
  const project = await (await request.get(`${API}/projects/${slug}`)).json();
  project.scenes = project.scenes.map((s: Record<string, unknown>) => ({
    ...s,
    voice: 'Muỗi đốt người.',
  }));
  expect((await request.put(`${API}/projects/${slug}`, { data: project })).ok()).toBeTruthy();
  return slug;
}
