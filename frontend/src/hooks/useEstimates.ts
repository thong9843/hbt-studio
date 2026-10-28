import { useQuery } from '@tanstack/react-query';
import { api } from '../api/endpoints';
import type { Fps, Project } from '../api/types';
import { vi } from '../i18n/vi';
import {
  estimateSeconds,
  formatEstimate,
  fullVideoSeconds,
  type RenderKind,
} from '../utils/estimate';

export const HEAD_PREVIEW_SECONDS = 10;
const FPS: Fps[] = [30, 50, 60];

export function projectFps(project: Pick<Project, 'settings'>): Fps {
  return (FPS as number[]).includes(project.settings.fps) ? (project.settings.fps as Fps) : 50;
}

/**
 * Ước tính thời gian dựng từ lịch sử `/renders`: lấy một lần khi mở màn, làm mới khi job kết thúc
 * (job invalid khoá `['renders', slug]`), không poll (13.B3.2 luật 6).
 */
export function useEstimates(project: Pick<Project, 'slug' | 'scenes' | 'settings'>) {
  const renders = useQuery({
    queryKey: ['renders', project.slug],
    queryFn: () => api.listRenders(project.slug),
    retry: false,
  });
  const history = renders.data ?? [];
  const full = fullVideoSeconds(history, project.scenes.length);
  const estimate = (kind: RenderKind): number => estimateSeconds(kind, history, full);
  return { history, loaded: renders.isSuccess, estimate };
}

/** "Xem nhanh ≈ 40 giây · Bản đẹp 50 fps ≈ 2 phút 30 giây"; rỗng khi chưa lấy được lịch sử. */
export function useEstimateLine(project: Pick<Project, 'slug' | 'scenes' | 'settings'>): string {
  const { loaded, estimate } = useEstimates(project);
  if (!loaded) return '';
  const fps = projectFps(project);
  return vi.estimate.line(
    formatEstimate(estimate({ kind: 'head', seconds: HEAD_PREVIEW_SECONDS })),
    formatEstimate(estimate({ kind: 'final', fps })),
    fps,
  );
}
