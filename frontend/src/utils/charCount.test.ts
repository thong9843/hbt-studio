import { describe, expect, it } from 'vitest';
import type { LineSize } from '../api/types';
import cases from '../../../shared/char_cases.json';
import { LINE_CHAR_LIMIT, countChars, lineCount } from './charCount';

describe('line character counter (shared with backend K5)', () => {
  it('uses the same limits as the shared case file', () => {
    expect(LINE_CHAR_LIMIT).toEqual(cases.limits);
  });

  it.each(cases.cases)('$name', ({ size, text, count, warn }) => {
    const res = lineCount(size as LineSize, text);
    expect(res.count).toBe(count);
    expect(res.over).toBe(warn);
  });

  it('counts astral characters once and composes combining marks', () => {
    expect(countChars('😀😀😀')).toBe(3);
    expect(countChars('é')).toBe(1);
  });
});
