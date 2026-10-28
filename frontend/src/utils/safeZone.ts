/** Vùng an toàn TikTok trên khung 1080×1920: lớp y 100–1500 và mép phải 120 px (13.B2). */
export const FRAME = { w: 1080, h: 1920 } as const;
export const SAFE = { top: 100, bottom: 1500, right: 120 } as const;

/** Ba dải bị giao diện che, đổi sang phần trăm của khung xem trước. */
export function safeZoneBands() {
  const top = (SAFE.top / FRAME.h) * 100;
  const bottom = ((FRAME.h - SAFE.bottom) / FRAME.h) * 100;
  const right = (SAFE.right / FRAME.w) * 100;
  return { top, bottom, right };
}
