import { describe, expect, it } from 'vitest';
import { splitPublishBlocks } from './publish';

describe('splitPublishBlocks', () => {
  it('splits publish.txt on [Name] headers and trims bodies', () => {
    const text = '[TikTok]\nMuỗi #shorts\n\n[YouTube Shorts]\nTitle: A\nDescription: B\n';
    expect(splitPublishBlocks(text)).toEqual([
      { name: 'TikTok', body: 'Muỗi #shorts' },
      { name: 'YouTube Shorts', body: 'Title: A\nDescription: B' },
    ]);
  });

  it('returns nothing without headers and keeps empty blocks', () => {
    expect(splitPublishBlocks('chỉ có chữ')).toEqual([]);
    expect(splitPublishBlocks('[TikTok]\n\n\n[YouTube Shorts]\nX')[0].body).toBe('');
  });
});
