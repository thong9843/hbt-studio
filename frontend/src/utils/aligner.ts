import type { AlignerInfo } from '../api/types';
import { vi } from '../i18n/vi';

/** "Whisper small · CPU", "Khoảng lặng"; tên lạ (bản ghi cũ) giữ nguyên. */
export function alignerLabel(aligner: string | null, info?: AlignerInfo | null): string {
  if (aligner === 'whisper') {
    const device = info?.device === 'cuda' ? vi.aligner.gpu : vi.aligner.cpu;
    return info?.model ? `${vi.aligner.whisper} ${info.model} · ${device}` : vi.aligner.whisper;
  }
  if (aligner === 'silence') return vi.aligner.silence;
  return aligner ?? '—';
}

/** Dòng giải thích dưới nhãn: tỉ lệ khớp, bậc đã bỏ qua, hoặc lý do rơi về khoảng lặng. */
export function alignerNotes(aligner: string | null, info?: AlignerInfo | null): string[] {
  const R = vi.export.result;
  const notes: string[] = [];
  if (aligner === 'whisper' && info?.match_ratio !== undefined) {
    notes.push(R.alignerMatch(`${(info.match_ratio * 100).toFixed(1).replace('.', ',')}%`));
  }
  if (info?.skipped?.length) notes.push(R.alignerSkipped(info.skipped.join('; ')));
  if (aligner === 'silence' && info?.whisper_error) {
    notes.push(R.alignerFallback(info.whisper_error));
  }
  return notes;
}
