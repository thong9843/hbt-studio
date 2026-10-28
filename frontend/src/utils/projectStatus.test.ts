import { describe, expect, it } from 'vitest';
import type { RenderSummary } from '../api/types';
import { projectImage, projectStatus } from './projectStatus';

const render = (over: Partial<RenderSummary> = {}): RenderSummary => ({
  job_id: 'a',
  preview: false,
  fps: 50,
  duration: 40,
  created_at: '2026-10-22T10:00:00',
  video: null,
  ...over,
});

describe('projectStatus', () => {
  it('"Đã xuất · fps" when a final render exists, even if a newer preview exists', () => {
    const s = projectStatus({
      error: null,
      last_final: render({ fps: 60 }),
      last_render: render({ preview: true, fps: 50 }),
    });
    expect(s).toEqual({ kind: 'final', label: 'Đã xuất · 60 fps' });
  });

  it('drops the fps part when the render did not record it', () => {
    const s = projectStatus({ error: null, last_final: render({ fps: null }), last_render: null });
    expect(s.label).toBe('Đã xuất');
  });

  it('"Đã xem nhanh" when only a preview exists', () => {
    const s = projectStatus({
      error: null,
      last_final: null,
      last_render: render({ preview: true }),
    });
    expect(s).toEqual({ kind: 'preview', label: 'Đã xem nhanh' });
  });

  it('"Chưa dựng" with no render at all', () => {
    expect(projectStatus({ error: null, last_final: null, last_render: null })).toEqual({
      kind: 'none',
      label: 'Chưa dựng',
    });
  });

  it('an unreadable project is flagged before anything else', () => {
    const s = projectStatus({ error: 'hỏng', last_final: render(), last_render: render() });
    expect(s.kind).toBe('broken');
  });
});

describe('projectImage', () => {
  it('prefers the cover, then scene 1, then nothing', () => {
    expect(projectImage({ cover: '/c.jpg', thumb: '/t.png' })).toBe('/c.jpg');
    expect(projectImage({ cover: null, thumb: '/t.png' })).toBe('/t.png');
    expect(projectImage({ cover: null, thumb: null })).toBeNull();
  });
});
