import { useQuery } from '@tanstack/react-query';
import { api } from '../api/endpoints';

export interface Covers {
  cover: string;
  youtube: string;
}

/**
 * Hai file bìa (9:16 và 3:2) của lần dựng gần nhất có đủ cả hai. `undefined` = chưa biết (đang
 * tải hoặc chưa bật), `null` = chưa lần nào có bìa. Dùng chung khoá `['renders', slug]` với lịch sử.
 */
export function useLatestCovers(slug: string, enabled = true): Covers | null | undefined {
  const renders = useQuery({
    queryKey: ['renders', slug],
    queryFn: () => api.listRenders(slug),
    enabled,
    retry: false,
  });
  if (!renders.isSuccess) return undefined;
  const found = renders.data.find((r) => r.cover && r.youtube_cover);
  return found?.cover && found.youtube_cover
    ? { cover: found.cover, youtube: found.youtube_cover }
    : null;
}
