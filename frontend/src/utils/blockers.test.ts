import { describe, expect, it } from 'vitest';
import { project, scene } from '../test/project';
import { primaryActionState, renderBlockers } from './blockers';
import { safeZoneBands } from './safeZone';

describe('primary action state', () => {
  it('is enabled when every scene has an image and the voice is set', () => {
    const p = project({
      voice: 'voice.wav',
      scenes: [scene({ image: 'a.png' }), scene({ image: 'b.png' }), scene({ image: 'c.png' })],
    });
    expect(renderBlockers(p)).toEqual([]);
    expect(primaryActionState(p)).toEqual({ enabled: true });
  });

  it('names the first scenes without an image (1-based) and the missing voice', () => {
    const p = project({ voice: null });
    expect(renderBlockers(p)).toEqual(['Thiếu ảnh cảnh 3', 'Thiếu giọng đọc']);
    expect(primaryActionState(p)).toEqual({
      enabled: false,
      reason: 'Thiếu ảnh cảnh 3 · Thiếu giọng đọc',
    });
  });

  it('lists several missing scenes in order', () => {
    const p = project({
      voice: { file: 'v.wav' },
      scenes: [scene(), scene({ image: 'x' }), scene()],
    });
    expect(renderBlockers(p)).toEqual(['Thiếu ảnh cảnh 1, 3']);
  });
});

describe('safe zone bands', () => {
  it('turns y 100–1500 and the 120 px right edge into percentages of the 1080×1920 frame', () => {
    const b = safeZoneBands();
    expect(b.top).toBeCloseTo(5.2083, 3);
    expect(b.bottom).toBeCloseTo(21.875, 3);
    expect(b.right).toBeCloseTo(11.1111, 3);
  });
});
