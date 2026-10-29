import type { ProjectKind } from '../api/types';

/** Đường dẫn mở một dự án: PostV có màn riêng, video HBT mở trình soạn cảnh. */
export function projectHref(p: { slug: string; kind?: ProjectKind }): string {
  return p.kind === 'postv' ? `/postv/${p.slug}` : `/p/${p.slug}`;
}
