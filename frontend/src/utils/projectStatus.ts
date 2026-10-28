import type { ProjectSummary } from '../api/types';
import { vi } from '../i18n/vi';

export type ProjectStatusKind = 'final' | 'preview' | 'none' | 'broken';

export interface ProjectStatus {
  kind: ProjectStatusKind;
  label: string;
}

/**
 * Nhãn lưới dự án (IMPLEMENT 13.B2): "Đã xuất · fps" nếu có bản đẹp; không có thì
 * "Đã xem nhanh" nếu có lần dựng nào; còn lại "Chưa dựng".
 */
export function projectStatus(
  p: Pick<ProjectSummary, 'error' | 'last_final' | 'last_render'>,
): ProjectStatus {
  const t = vi.projects.status;
  if (p.error) return { kind: 'broken', label: vi.projects.broken };
  if (p.last_final) return { kind: 'final', label: t.final(p.last_final.fps) };
  if (p.last_render) return { kind: 'preview', label: t.preview };
  return { kind: 'none', label: t.none };
}

/** Ảnh thẻ: bìa của lần dựng gần nhất có bìa, rồi ảnh cảnh 1; không có thì null (ô HBT). */
export function projectImage(p: Pick<ProjectSummary, 'cover' | 'thumb'>): string | null {
  return p.cover ?? p.thumb ?? null;
}
