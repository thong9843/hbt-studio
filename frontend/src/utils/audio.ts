import type { MusicEntry, RenderRecord } from '../api/types';

/** Nghe thử đoạn nhạc dài chừng này (giây). */
export const PREVIEW_SECONDS = 10;

/**
 * Giây app đã tự chọn ở lần dựng gần nhất. Chỉ tin khi nhạc hiện tại vẫn là nhạc đã dùng
 * (`music_matches_current`, IMPLEMENT 6.1 P3); ngược lại `null` và dòng "Lần trước" ẩn đi.
 */
export function lastAutoStart(latest: RenderRecord | undefined): number | null {
  if (!latest || latest.music_start_source !== 'auto' || latest.music_start === null) return null;
  return latest.music_matches_current ? latest.music_start : null;
}

/** Dòng ghi công mà backend tự điền khi chọn bài từ thư viện (`MusicEntry.credit`). */
export function creditOf(entry: MusicEntry): string {
  return `${entry.title} – ${entry.artist} (${entry.source})`;
}

/** Các tâm trạng có thật trong thư viện, không trùng, theo thứ tự chữ. */
export function libraryMoods(entries: MusicEntry[]): string[] {
  const set = new Set<string>();
  for (const e of entries) for (const m of e.moods) if (m.trim()) set.add(m.trim());
  return [...set].sort((a, b) => a.localeCompare(b, 'vi'));
}
