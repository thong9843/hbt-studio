import { describe, expect, it } from 'vitest';
import type { RenderSummary } from '../api/types';
import { project, scene } from '../test/project';
import { latestExport, readiness } from './readiness';

describe('readiness', () => {
  it('counts scenes that have an image', () => {
    const r = readiness(project());
    expect(r.images).toEqual({ done: 2, total: 3 });
    expect(r.voice).toBe(false);
    expect(r.music).toBe(false);
    expect(r.cover).toBe(false);
  });

  it('knows voice (string or object), music file and cover', () => {
    const base = {
      thumbnail: { scene: 1, lines: ['a', 'b'], series: '', accent: '#FFD43B' },
      music: { file: 'music.mp3', start: null, credit: '' },
    };
    expect(readiness(project({ ...base, voice: 'voice.wav' }))).toMatchObject({
      voice: true,
      music: true,
      cover: true,
    });
    expect(readiness(project({ ...base, voice: { file: 'voice.wav' } })).voice).toBe(true);
    expect(readiness(project({ ...base, voice: { file: '' } })).voice).toBe(false);
  });

  it('music without a file does not count', () => {
    expect(readiness(project({ music: { file: null, start: null, credit: '' } })).music).toBe(
      false,
    );
  });

  it('a project with no scenes has 0/0 images', () => {
    expect(readiness(project({ scenes: [scene()] })).images).toEqual({ done: 0, total: 1 });
  });
});

const render = (created_at: string, over: Partial<RenderSummary> = {}): RenderSummary => ({
  job_id: created_at,
  preview: false,
  fps: 50,
  duration: 40,
  created_at,
  video: null,
  ...over,
});

describe('latestExport', () => {
  it('returns null when nothing was rendered', () => {
    expect(latestExport([{ last_final: null, last_render: null }])).toBeNull();
    expect(latestExport([])).toBeNull();
  });

  it('picks the newest render across projects, preferring each project’s final render', () => {
    const a = { id: 'a', last_final: render('2026-10-20T10:00:00Z'), last_render: null };
    const b = {
      id: 'b',
      last_final: render('2026-10-22T10:00:00Z'),
      last_render: render('2026-10-25T10:00:00Z', { preview: true }),
    };
    const c = { id: 'c', last_final: null, last_render: render('2026-10-21T10:00:00Z') };
    const best = latestExport([a, b, c]);
    expect(best?.project.id).toBe('b');
    expect(best?.render.created_at).toBe('2026-10-22T10:00:00Z');
  });

  it('falls back to a preview when the project has no final render', () => {
    const only = {
      last_final: null,
      last_render: render('2026-10-21T10:00:00Z', { preview: true }),
    };
    expect(latestExport([only])?.render.preview).toBe(true);
  });
});
