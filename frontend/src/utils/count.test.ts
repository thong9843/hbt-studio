import { describe, expect, it } from 'vitest';
import cases from '../../../shared/count_cases.json';
import { formatCount, parseCount } from './count';

describe('parseCount (shared with backend counts.py)', () => {
  it.each(cases.parse)('$in', ({ in: input, out }) => {
    expect(parseCount(input)).toBe(out);
  });
});

describe('formatCount', () => {
  it.each(cases.format)('$n', ({ n, out }) => {
    expect(formatCount(n)).toBe(out);
  });

  it('prints nothing for null / undefined', () => {
    expect(formatCount(null)).toBe('');
    expect(formatCount(undefined)).toBe('');
  });

  it('round-trips what it prints', () => {
    for (const n of [351, 1800, 27600, 619000, 1500000]) {
      expect(parseCount(formatCount(n))).toBe(n);
    }
  });
});
