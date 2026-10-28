import { createContext, useContext } from 'react';
import type { Job, RenderOptions } from '../api/types';

export interface RenderJobApi {
  /** Dự án của job gần nhất (đang chạy hoặc vừa xong); `null` khi chưa dựng gì trong phiên. */
  slug: string | null;
  jobId: string | null;
  /** Đang xếp hàng hoặc đang dựng: SSE đang mở. */
  running: boolean;
  /** Đang gọi `POST /render`. */
  starting: boolean;
  percent: number;
  step: string;
  message: string;
  /** Job đã kết thúc (xong / lỗi / huỷ); `null` khi đang chạy hoặc chưa có. */
  finished: Job | null;
  connectionError: string | null;
  /** Tuỳ chọn của lần dựng gần nhất (để xác nhận cắt đuôi dài rồi dựng lại). */
  options: RenderOptions;
  /** Tổng thời gian ước tính của job đang chạy (giây); `null` = chưa ước tính được. */
  estimateSeconds: number | null;
  /** Lỗi API (409 đang dựng, 422 thiếu nguyên liệu…) được ném lại cho nơi gọi. */
  start: (slug: string, options: RenderOptions, estimateSeconds?: number | null) => Promise<void>;
  cancel: () => Promise<void>;
}

const IDLE: RenderJobApi = {
  slug: null,
  jobId: null,
  running: false,
  starting: false,
  percent: 0,
  step: '',
  message: '',
  finished: null,
  connectionError: null,
  options: {},
  estimateSeconds: null,
  start: () => Promise.reject(new Error('RenderJobProvider chưa được gắn')),
  cancel: () => Promise.resolve(),
};

export const RenderJobContext = createContext<RenderJobApi>(IDLE);

export const useRenderJob = () => useContext(RenderJobContext);
