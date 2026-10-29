/**
 * Đọc/hiển thị số liệu kiểu mạng xã hội (`27.6K`, `1,5K`, `2M`, `1.200`).
 * Dùng chung bộ ca `shared/count_cases.json` với backend (`hbt/postv/counts.py`).
 */
export function parseCount(raw: string): number | null {
  const s = raw.trim().toLowerCase().replace(/\s+/g, '');
  if (!s) return null;
  if (/^\d+$/.test(s)) return Number(s);
  if (/^\d{1,3}([.,]\d{3})+$/.test(s)) return Number(s.replace(/[.,]/g, ''));
  const m = /^(\d+(?:[.,]\d+)?)([km])$/.exec(s);
  if (m) return Math.round(Number(m[1].replace(',', '.')) * (m[2] === 'k' ? 1e3 : 1e6));
  return null;
}

const oneDecimal = (v: number) => (Math.round(v * 10) / 10).toString().replace('.', ',');

/** 27600 → "27,6K", 1500000 → "1,5M", 351 → "351"; rỗng cho null. */
export function formatCount(n: number | null | undefined): string {
  if (n === null || n === undefined) return '';
  if (n >= 1e6 || Math.round(n / 100) / 10 >= 1000) return `${oneDecimal(n / 1e6)}M`;
  if (n >= 1e3) return `${oneDecimal(n / 1e3)}K`;
  return String(n);
}
