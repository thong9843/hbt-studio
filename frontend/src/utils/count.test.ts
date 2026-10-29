import { describe, expect, it } from 'vitest';
import cases from '../../../shared/count_cases.json';
import { formatCount, parseCount } from './count';

describe('parseCount (shared with backend counts.py)', () => {
  it.each(cases)('$in', ({ in: input, out }) => {
    expect(parseCount(input)).toBe(out);
  });
});

describe('formatCount', () => {
  it.each([
    [null, ''],
    [undefined, ''],
    [0, '0'],
    [351, '351'],
    [1000, '1K'],
    [1800, '1,8K'],
    [27600, '27,6K'],
    [619000, '619K'],
    [999950, '1M'],
    [1500000, '1,5M'],
    [2000000, '2M'],
  ])('%s → %s', (n, text) => {
    expect(formatCount(n)).toBe(text);
  });

  it('round-trips what it prints', () => {
    for (const n of [351, 1800, 27600, 619000, 1500000]) {
      expect(parseCount(formatCount(n))).toBe(n);
    }
  });
});
