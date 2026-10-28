import { describe, expect, it } from 'vitest';
import {
  DEFAULT_COEFFICIENT,
  estimateSeconds,
  formatEstimate,
  fullVideoSeconds,
  remainingSeconds,
} from './estimate';

const rec = (over: Record<string, unknown>) => ({
  preview: false,
  preview_seconds: null,
  fps: 50,
  duration: 50,
  render_seconds: 150,
  created_at: '2026-10-20T10:00:00Z',
  ...over,
});

describe('estimateSeconds', () => {
  it('uses the default coefficient when there is no history (13.B5)', () => {
    expect(estimateSeconds({ kind: 'final', fps: 50 }, [], 50)).toBe(150);
    expect(estimateSeconds({ kind: 'final', fps: 60 }, [], 50)).toBeCloseTo(210);
    expect(estimateSeconds({ kind: 'head', seconds: 10 }, [], 99)).toBe(
      DEFAULT_COEFFICIENT.head * 10,
    );
  });

  it('takes the median of the 3 newest renders of the same kind, per video second', () => {
    const history = [
      rec({ render_seconds: 100, created_at: '2026-10-21T10:00:00Z' }), // 2,0
      rec({ render_seconds: 200, created_at: '2026-10-22T10:00:00Z' }), // 4,0
      rec({ render_seconds: 150, created_at: '2026-10-23T10:00:00Z' }), // 3,0
      rec({ render_seconds: 900, created_at: '2026-10-01T10:00:00Z' }), // quá cũ
    ];
    expect(estimateSeconds({ kind: 'final', fps: 50 }, history, 40)).toBeCloseTo(120);
  });

  it('only compares the same kind: head and each fps are separate', () => {
    const history = [
      rec({ fps: 60, render_seconds: 500 }),
      rec({ preview: true, preview_seconds: 10, duration: 10, render_seconds: 20, fps: 30 }),
      rec({ preview: true, preview_seconds: null, duration: 40, render_seconds: 80, fps: 30 }),
    ];
    expect(estimateSeconds({ kind: 'final', fps: 50 }, history, 50)).toBe(150); // mặc định
    expect(estimateSeconds({ kind: 'head', seconds: 10 }, history, 50)).toBe(20);
  });

  it('skips old renders that lack render_seconds or duration', () => {
    const history = [rec({ render_seconds: null }), rec({ duration: null })];
    expect(estimateSeconds({ kind: 'final', fps: 50 }, history, 50)).toBe(150);
  });
});

describe('fullVideoSeconds', () => {
  it('uses the newest known full duration, else scenes × 6 s', () => {
    const history = [
      rec({ duration: 44, created_at: '2026-10-20T10:00:00Z' }),
      rec({ duration: 48, created_at: '2026-10-22T10:00:00Z' }),
      rec({ preview: true, preview_seconds: 10, duration: 10, created_at: '2026-10-23T10:00:00Z' }),
    ];
    expect(fullVideoSeconds(history, 8)).toBe(48);
    expect(fullVideoSeconds([], 8)).toBe(48);
    expect(fullVideoSeconds([], 5)).toBe(30);
  });
});

describe('remainingSeconds / formatEstimate', () => {
  it('is unknown at 0% and shrinks linearly with progress', () => {
    expect(remainingSeconds(100, 0)).toBeNull();
    expect(remainingSeconds(100, 25)).toBe(75);
    expect(remainingSeconds(100, 100)).toBe(0);
    expect(remainingSeconds(0, 50)).toBeNull();
  });

  it('formats seconds and minutes in Vietnamese', () => {
    expect(formatEstimate(0.2)).toBe('1 giây');
    expect(formatEstimate(45)).toBe('45 giây');
    expect(formatEstimate(80)).toBe('1 phút 20 giây');
    expect(formatEstimate(121)).toBe('2 phút');
  });
});
