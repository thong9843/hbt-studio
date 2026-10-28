import { describe, expect, it } from 'vitest';
import { parseHashtags } from './hashtags';

describe('parseHashtags', () => {
  it('drops the leading # and splits on spaces or commas', () => {
    expect(parseHashtags('#muoi  #khoahoc, dem')).toEqual(['muoi', 'khoahoc', 'dem']);
  });

  it('ignores empty pieces and lone #', () => {
    expect(parseHashtags(' # ,  ')).toEqual([]);
    expect(parseHashtags('')).toEqual([]);
  });

  it('normalises to NFC like the backend', () => {
    expect(parseHashtags('#muỗi')[0]).toBe('muỗi');
    expect(parseHashtags('#muỗi')[0]).toBe('muỗi');
  });
});
