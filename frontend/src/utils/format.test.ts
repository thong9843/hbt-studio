import { describe, expect, it } from 'vitest';
import { formatBytes, formatDateTime, formatDuration } from './format';

describe('format', () => {
  it('formats durations as m:ss', () => {
    expect(formatDuration(0)).toBe('0:00');
    expect(formatDuration(83.4)).toBe('1:23');
    expect(formatDuration(-5)).toBe('0:00');
  });

  it('formats sizes', () => {
    expect(formatBytes(100)).toBe('1 KB');
    expect(formatBytes(2048)).toBe('2 KB');
    expect(formatBytes(5.5 * 1024 * 1024)).toBe('5.5 MB');
  });

  it('formats a local date time and leaves junk alone', () => {
    expect(formatDateTime('2026-10-22T14:05:00')).toBe('22/10/2026 14:05');
    expect(formatDateTime('hôm qua')).toBe('hôm qua');
  });
});
