import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { deflateSync } from 'node:zlib';

import { expect, type APIRequestContext } from '@playwright/test';

export const API = 'http://127.0.0.1:8000/api';
export const SAMPLE = join(process.cwd(), 'workspace', 'samples', 'muoi');

/**
 * Xoá dự án thử bằng DELETE. Job vừa huỷ có thể còn giữ file nên máy chủ trả 409:
 * thử lại tới 20 lần (mỗi lần 500 ms); cuối cùng phải là 204.
 */
export async function deleteProject(request: APIRequestContext, slug: string): Promise<void> {
  if (!slug) return;
  // Nếu có job đang chạy cho slug này thì gọi huỷ job, đợi hết rồi mới xoá
  try {
    const res = await request.get(`${API}/jobs`);
    if (res.ok()) {
      const jobs = (await res.json()) as Array<{ id: string; slug: string }>;
      for (const j of jobs) {
        if (j.slug === slug) {
          await request.post(`${API}/jobs/${j.id}/cancel`).catch(() => {});
        }
      }
    }
  } catch {
    // Bỏ qua lỗi kết nối
  }
  let status = 0;
  for (let i = 0; i < 30; i++) {
    status = (await request.delete(`${API}/projects/${slug}`)).status();
    if (status !== 409) break;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  expect([204, 404], `DELETE /projects/${slug}`).toContain(status);
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

/** PNG một màu `w`×`h` (tạo khi chạy, vài trăm byte); `rgb` là [r, g, b]. */
export function solidPng(w: number, h: number, rgb: [number, number, number]): Buffer {
  const crcTable = Array.from({ length: 256 }, (_, n) => {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    return c >>> 0;
  });
  const crc = (buf: Buffer) => {
    let c = 0xffffffff;
    for (const b of buf) c = crcTable[(c ^ b) & 0xff] ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
  };
  const chunk = (type: string, data: Buffer) => {
    const body = Buffer.concat([Buffer.from(type, 'ascii'), data]);
    const out = Buffer.alloc(body.length + 8);
    out.writeUInt32BE(data.length, 0);
    body.copy(out, 4);
    out.writeUInt32BE(crc(body), body.length + 4);
    return out;
  };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0);
  ihdr.writeUInt32BE(h, 4);
  ihdr[8] = 8; // 8 bit
  ihdr[9] = 2; // RGB
  const row = Buffer.concat([
    Buffer.from([0]),
    Buffer.from(Array.from({ length: w }, () => rgb).flat()),
  ]);
  const raw = Buffer.concat(Array.from({ length: h }, () => row));
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(raw)),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}
