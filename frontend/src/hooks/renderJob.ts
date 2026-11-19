import { createContext, useContext } from 'react';
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

export interface RenderJobApi {
  /** Dự án của job gần nhất (đang chạy hoặc vừa xong); `null` khi chưa dựng gì trong phiên. */
  slug: string | null;
  jobId: string | null;
  /** Loại job đang theo dõi (`stickv`, `preview`, `final`, ...). */
  kind: ActiveJob['kind'] | null;
  /** Đang xếp hàng hoặc đang dựng: SSE đang mở. */
  running: boolean;
  /** Đang gọi `POST /render`. */
  starting: boolean;
  percent: number;
  step: string;
  stage: string;
  message: string;
  currentBeat: number | null;
  totalBeats: number | null;
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
}

const IDLE: RenderJobApi = {
  slug: null,
  jobId: null,
  kind: null,
  running: false,
  starting: false,
  percent: 0,
  step: '',
  stage: '',
  message: '',
  currentBeat: null,
  totalBeats: null,
  startedAt: null,
  finished: null,
  connectionError: null,
  options: {},
  estimateSeconds: null,
  start: () => Promise.reject(new Error('RenderJobProvider chưa được gắn')),
  attachJob: () => undefined,
  cancel: () => Promise.resolve(),
};

export const RenderJobContext = createContext<RenderJobApi>(IDLE);

export const useRenderJob = () => useContext(RenderJobContext);
