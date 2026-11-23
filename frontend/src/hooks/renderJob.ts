import { createContext, useContext, useMemo, useSyncExternalStore } from 'react';
import type { ActiveJob, Job, RenderOptions } from '../api/types';

export interface AttachJobInput {
  jobId: string;
  slug: string;
  kind: ActiveJob['kind'];
  preview?: boolean;
  progress?: number;
  step?: string;
  stage?: string;
  message?: string;
  currentBeat?: number | null;
  totalBeats?: number | null;
  startedAt?: number | null;
  estimateSeconds?: number | null;
}

export interface RenderJobProgressSnapshot {
  percent: number;
  step: string;
  stage: string;
  message: string;
  currentBeat: number | null;
  totalBeats: number | null;
}

export interface RenderJobProgressStore {
  getSnapshot: () => RenderJobProgressSnapshot;
  setSnapshot: (next: RenderJobProgressSnapshot) => void;
  subscribe: (listener: () => void) => () => void;
}

export const EMPTY_PROGRESS_SNAPSHOT: RenderJobProgressSnapshot = {
  percent: 0,
  step: '',
  stage: '',
  message: '',
  currentBeat: null,
  totalBeats: null,
};

export function createRenderJobProgressStore(
  initial: RenderJobProgressSnapshot = EMPTY_PROGRESS_SNAPSHOT,
): RenderJobProgressStore {
  let current = initial;
  const listeners = new Set<() => void>();
  return {
    getSnapshot: () => current,
    setSnapshot: (next: RenderJobProgressSnapshot) => {
      if (
        current.percent === next.percent &&
        current.step === next.step &&
        current.stage === next.stage &&
        current.message === next.message &&
        current.currentBeat === next.currentBeat &&
        current.totalBeats === next.totalBeats
      ) {
        return;
      }
      current = next;
      for (const listener of listeners) {
        listener();
      }
    },
    subscribe: (listener: () => void) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}

export interface RenderJobStatusApi {
  /** Dự án của job gần nhất (đang chạy hoặc vừa xong); `null` khi chưa dựng gì trong phiên. */
  slug: string | null;
  jobId: string | null;
  /** Loại job đang theo dõi (`stickv`, `preview`, `final`, ...). */
  kind: ActiveJob['kind'] | null;
  /** Đang xếp hàng hoặc đang dựng: SSE đang mở. */
  running: boolean;
  /** Đang gọi `POST /render`. */
  starting: boolean;
  startedAt: number | null;
  /** Job đã kết thúc (xong / lỗi / huỷ); `null` khi đang chạy hoặc chưa có. */
  finished: Job | null;
  connectionError: string | null;
  /** Tuỳ chọn của lần dựng gần nhất (để xác nhận cắt đuôi dài rồi dựng lại). */
  options: RenderOptions;
  /** Tổng thời gian ước tính của job đang chạy (giây); `null` = chưa ước tính được. */
  estimateSeconds: number | null;
  /** Lỗi API (409 đang dựng, 422 thiếu nguyên liệu…) được ném lại cho nơi gọi. */
  start: (slug: string, options: RenderOptions, estimateSeconds?: number | null) => Promise<void>;
  /** Nối/giữ một job đã khởi tạo (vd StickV) vào luồng SSE toàn cục. */
  attachJob: (input: AttachJobInput) => void;
  cancel: () => Promise<void>;
  /** External store cô lập tiến độ % nhảy liên tục để trang lớn không bao giờ re-render. */
  progressStore: RenderJobProgressStore;
}

export type RenderJobApi = Omit<RenderJobStatusApi, 'progressStore'> & RenderJobProgressSnapshot;

const IDLE_STORE = createRenderJobProgressStore();

const IDLE_STATUS: RenderJobStatusApi = {
  slug: null,
  jobId: null,
  kind: null,
  running: false,
  starting: false,
  startedAt: null,
  finished: null,
  connectionError: null,
  options: {},
  estimateSeconds: null,
  start: () => Promise.reject(new Error('RenderJobProvider chưa được gắn')),
  attachJob: () => undefined,
  cancel: () => Promise.resolve(),
  progressStore: IDLE_STORE,
};

export const RenderJobContext = createContext<RenderJobStatusApi>(IDLE_STATUS);

/**
 * Chỉ đọc trạng thái vòng đời job (`running`, `kind`, `slug`, `finished`, `attachJob`, `cancel`...).
 * KHÔNG đăng ký lắng nghe `percent`/`step` nên component gọi hook này re-render ĐÚNG 0 LẦN khi tiến độ nhảy 1% → 100%.
 */
export function useRenderJobStatus(): RenderJobStatusApi {
  return useContext(RenderJobContext);
}

/**
 * Chỉ đăng ký nhận `percent`, `step`, `stage`, `message`, `currentBeat`, `totalBeats` qua `useSyncExternalStore`.
 * Chỉ dùng ở các widget tiến độ siêu nhỏ (`ExportPopover`, `GlobalJobDock`, `SidebarRenderCard`).
 */
export function useRenderJobProgress(): RenderJobProgressSnapshot {
  const { progressStore } = useContext(RenderJobContext);
  return useSyncExternalStore(
    progressStore.subscribe,
    progressStore.getSnapshot,
    progressStore.getSnapshot,
  );
}

/** Đúng trang đang hiển thị trực tiếp tiến độ của job active (ẩn Dock/Sidebar lặp). */
export function isOnActiveJobPage(
  pathname: string,
  kind: ActiveJob['kind'] | null,
  slug: string | null,
): boolean {
  if (kind === 'stickv' && pathname.startsWith('/stickv')) {
    return true;
  }
  if (
    (kind === 'preview' || kind === 'final') &&
    slug &&
    pathname.startsWith(`/p/${slug}/export`)
  ) {
    return true;
  }
  return false;
}

/**
 * Hook đầy đủ tương thích ngược (gộp cả trạng thái vòng đời + tiến độ tức thời).
 */
export function useRenderJob(): RenderJobApi {
  const status = useRenderJobStatus();
  const progress = useRenderJobProgress();
  return useMemo(
    () => ({
      slug: status.slug,
      jobId: status.jobId,
      kind: status.kind,
      running: status.running,
      starting: status.starting,
      startedAt: status.startedAt,
      finished: status.finished,
      connectionError: status.connectionError,
      options: status.options,
      estimateSeconds: status.estimateSeconds,
      start: status.start,
      attachJob: status.attachJob,
      cancel: status.cancel,
      percent: progress.percent,
      step: progress.step,
      stage: progress.stage,
      message: progress.message,
      currentBeat: progress.currentBeat,
      totalBeats: progress.totalBeats,
    }),
    [status, progress],
  );
}
