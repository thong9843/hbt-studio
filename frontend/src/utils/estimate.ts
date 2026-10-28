import type { Fps, RenderRecord } from '../api/types';

/** Loại lần dựng để ước tính: Xem nhanh 10 s đầu / bản đẹp theo fps. */
export type RenderKind = { kind: 'head'; seconds: number } | { kind: 'final'; fps: Fps };

type Past = Pick<
  RenderRecord,
  'preview' | 'preview_seconds' | 'fps' | 'duration' | 'render_seconds' | 'created_at'
>;

/**
 * Hệ số mặc định khi chưa có lịch sử: giây dựng trên mỗi giây video (máy cũ).
 * Bản đẹp 50 fps ≈ 3, 60 fps ≈ 4,2 (IMPLEMENT 13.B5); 30 fps suy theo tỉ lệ (0,06 × fps).
 * Xem nhanh 10 s đầu ≈ 4 (42 s nguội cho 10 s, M2).
 */
export const DEFAULT_COEFFICIENT = {
  head: 4,
  final: { 30: 1.8, 50: 3, 60: 4.2 } satisfies Record<Fps, number>,
} as const;

/** Số giây video giả định mỗi cảnh khi dự án chưa từng dựng cả video. */
export const FALLBACK_SECONDS_PER_SCENE = 6;

function sameKind(r: Past, k: RenderKind): boolean {
  if (k.kind === 'head') return r.preview && r.preview_seconds !== null;
  return !r.preview && r.fps === k.fps;
}

function median(values: number[]): number {
  const v = [...values].sort((a, b) => a - b);
  const mid = Math.floor(v.length / 2);
  return v.length % 2 ? v[mid] : (v[mid - 1] + v[mid]) / 2;
}

/** Bản dựng cũ không ghi `render_seconds` hoặc `duration` thì bỏ qua. */
function usable(r: Past): r is Past & { render_seconds: number; duration: number } {
  return (
    typeof r.render_seconds === 'number' &&
    r.render_seconds > 0 &&
    typeof r.duration === 'number' &&
    r.duration > 0
  );
}

/** Giây video của lần dựng cả video: lần gần nhất đã biết, không có thì số cảnh × 6 s. */
export function fullVideoSeconds(history: Past[], sceneCount: number): number {
  const known = history
    .filter((r) => (r.preview_seconds ?? null) === null && typeof r.duration === 'number')
    .sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
  return known?.duration ?? sceneCount * FALLBACK_SECONDS_PER_SCENE;
}

/**
 * Ước tính tổng thời gian dựng (giây): trung vị hệ số (giây dựng ÷ giây video) của 3 lần gần nhất
 * cùng loại, nhân với độ dài video sắp dựng. Chưa có lịch sử thì dùng hệ số mặc định.
 */
export function estimateSeconds(kind: RenderKind, history: Past[], videoSeconds: number): number {
  const recent = history
    .filter((r) => sameKind(r, kind) && usable(r))
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .slice(0, 3);
  const seconds = kind.kind === 'head' ? kind.seconds : videoSeconds;
  const coefficient = recent.length
    ? median(recent.map((r) => r.render_seconds! / r.duration!))
    : kind.kind === 'final'
      ? DEFAULT_COEFFICIENT.final[kind.fps]
      : DEFAULT_COEFFICIENT[kind.kind];
  return coefficient * seconds;
}

/** Thời gian còn lại; `null` khi tiến độ còn 0% (chưa đủ cơ sở). */
export function remainingSeconds(total: number, percent: number): number | null {
  if (!(percent > 0) || !(total > 0)) return null;
  return Math.max(0, total * (1 - Math.min(100, percent) / 100));
}

/** 45 → "45 giây"; 80 → "1 phút 20 giây" (từ 1 phút làm tròn 5 giây cho đỡ nhảy số). */
export function formatEstimate(seconds: number): string {
  const s = seconds < 60 ? Math.max(1, Math.round(seconds)) : Math.round(seconds / 5) * 5;
  if (s < 60) return `${s} giây`;
  const m = Math.floor(s / 60);
  const rest = s % 60;
  return rest ? `${m} phút ${rest} giây` : `${m} phút`;
}
