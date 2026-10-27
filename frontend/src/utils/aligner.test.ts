import { describe, expect, it } from 'vitest';
import { alignerLabel, alignerNotes } from './aligner';

describe('alignerLabel', () => {
  it('names the model and the device Whisper ran on', () => {
    expect(alignerLabel('whisper', { model: 'small', device: 'cpu' })).toBe('Whisper small · CPU');
    expect(alignerLabel('whisper', { model: 'large-v3', device: 'cuda' })).toBe(
      'Whisper large-v3 · GPU',
    );
  });

  it('copes with records that have no detail', () => {
    expect(alignerLabel('whisper')).toBe('Whisper');
    expect(alignerLabel('silence', null)).toBe('Khoảng lặng');
    expect(alignerLabel(null)).toBe('—');
    expect(alignerLabel('khac')).toBe('khac');
  });
});

describe('alignerNotes', () => {
  it('reports the match ratio and any skipped steps', () => {
    expect(
      alignerNotes('whisper', {
        match_ratio: 0.9712,
        skipped: ['large-v3 (cuda, int8_float16): lỗi lúc nạp model: x'],
      }),
    ).toEqual([
      'Khớp 97,1% âm tiết của kịch bản.',
      'Đã bỏ qua: large-v3 (cuda, int8_float16): lỗi lúc nạp model: x',
    ]);
  });

  it('says why Whisper was dropped when the silence fallback was used', () => {
    expect(alignerNotes('silence', { whisper_error: 'quá giới hạn 900 giây' })).toEqual([
      'Whisper không dùng được, đã căn theo khoảng lặng: quá giới hạn 900 giây',
    ]);
  });

  it('has nothing to add for a plain silence result', () => {
    expect(alignerNotes('silence', {})).toEqual([]);
    expect(alignerNotes('silence')).toEqual([]);
  });
});
