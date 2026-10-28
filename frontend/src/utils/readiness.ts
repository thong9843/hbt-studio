import type { Project, RenderSummary } from '../api/types';

export interface Readiness {
  images: { done: number; total: number };
  voice: boolean;
  music: boolean;
  cover: boolean;
}

/** Nguyên liệu đã có của dự án (chấm trên thẻ "Tiếp tục làm"). */
export function readiness(p: Pick<Project, 'scenes' | 'voice' | 'music' | 'thumbnail'>): Readiness {
  const voiceFile = typeof p.voice === 'string' ? p.voice : p.voice?.file;
  return {
    images: { done: p.scenes.filter((s) => s.image).length, total: p.scenes.length },
    voice: Boolean(voiceFile),
    music: Boolean(p.music?.file),
    cover: p.thumbnail !== null,
  };
}

/**
 * Lần xuất gần nhất trong mọi dự án: mỗi dự án lấy bản đẹp mới nhất, không có thì lần dựng
 * gần nhất; rồi chọn bản có `created_at` mới nhất.
 */
export function latestExport<
  T extends { last_final: RenderSummary | null; last_render: RenderSummary | null },
>(projects: T[]): { project: T; render: RenderSummary } | null {
  let best: { project: T; render: RenderSummary } | null = null;
  for (const project of projects) {
    const render = project.last_final ?? project.last_render;
    if (!render) continue;
    if (!best || Date.parse(render.created_at) > Date.parse(best.render.created_at))
      best = { project, render };
  }
  return best;
}
