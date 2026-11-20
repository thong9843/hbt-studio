import type { BackgroundEntry } from '../api/types';

/** Clip nhỏ hơn 1080×1920: dùng được (từ 720×1280) nhưng giao diện nhắc. */
export const isLowRes = (c: Pick<BackgroundEntry, 'width' | 'height'>) =>
  c.width < 1080 || c.height < 1920;
