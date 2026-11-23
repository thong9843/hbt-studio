/** Định dạng số thập phân an toàn — không bao giờ crash khi giá trị là undefined/null/NaN. */
export function safeFixed(val: unknown, digits = 1, fallback = '0'): string {
  return typeof val === 'number' && Number.isFinite(val) ? val.toFixed(digits) : fallback;
}

/** 83.4 → "1:23" */
export function formatDuration(seconds: number): string {
  const safe = typeof seconds === 'number' && Number.isFinite(seconds) ? seconds : 0;
  const total = Math.max(0, Math.round(safe));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

export function formatBytes(bytes: number): string {
  const safe = typeof bytes === 'number' && Number.isFinite(bytes) ? bytes : 0;
  if (safe < 1024 * 1024) return `${Math.max(1, Math.round(safe / 1024))} KB`;
  return `${safeFixed(safe / (1024 * 1024), 1)} MB`;
}

/** ISO → "22/10/2026 14:05" (giờ máy). */
export function formatDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** ISO → "22/10/2026" (giờ máy). */
export function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()}`;
}
