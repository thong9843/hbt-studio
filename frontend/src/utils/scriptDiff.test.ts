import { describe, expect, it } from 'vitest';
import type { ScriptCheck } from '../api/types';
import { appliedScenes, buildRows, hasSurplus, surplusScenes, untouched } from './scriptDiff';

const base = (over: Partial<ScriptCheck> = {}): ScriptCheck => ({
  ok: true,
  base_hash: 'h',
  counts: { json: 3, project: 3, after: 3 },
  errors: [],
  warnings: [],
  diff: [],
  realign_scenes: [],
  ...over,
});
const issue = (scene_index: number | null, code = 'K5') => ({
  code,
  scene_index,
  field: 'card',
  message: 'm',
});

describe('buildRows', () => {
  it('groups diff, errors and warnings by scene and sorts them', () => {
    const rows = buildRows(
      base({
        diff: [
          { scene_index: 2, field: 'card', before: 1, after: 2 },
          { scene_index: 0, field: 'punch', before: false, after: true },
          { scene_index: null, field: 'publish', before: {}, after: {} },
        ],
        warnings: [issue(2), issue(null, 'K9')],
        errors: [issue(0, 'K6')],
      }),
    );
    expect(rows.scenes.map((r) => r.sceneIndex)).toEqual([0, 2]);
    expect(rows.scenes[1].warnings).toHaveLength(1);
    expect(rows.scenes[0].errors[0].code).toBe('K6');
    expect(rows.whole.diffs).toHaveLength(1);
    expect(rows.whole.warnings).toHaveLength(1);
  });

  it('puts added scenes in their own bucket', () => {
    const rows = buildRows(
      base({
        diff: [
          { scene_index: 0, field: 'voice', before: 'a', after: 'b' },
          { scene_index: 3, field: 'scene', before: null, after: {} },
          { scene_index: 4, field: 'scene', before: null, after: {} },
        ],
        warnings: [issue(3, 'K9')],
      }),
    );
    expect(rows.scenes.map((r) => r.sceneIndex)).toEqual([0]);
    expect(rows.added.map((r) => r.sceneIndex)).toEqual([3, 4]);
  });
});

describe('scene counts', () => {
  it('applied = min(json, after)', () => {
    expect(appliedScenes(base({ counts: { json: 2, project: 3, after: 3 } }))).toBe(2);
    expect(appliedScenes(base({ counts: { json: 5, project: 3, after: 3 } }))).toBe(3);
    expect(appliedScenes(base({ counts: { json: 5, project: 3, after: 5 } }))).toBe(5);
  });

  it('surplus shows the add/trim choice once K2 is raised or extra is chosen', () => {
    const over = base({ counts: { json: 5, project: 3, after: 3 }, errors: [issue(null, 'K2')] });
    expect(surplusScenes(over)).toBe(2);
    expect(hasSurplus(over, null)).toBe(true);
    const chosen = base({ counts: { json: 5, project: 3, after: 5 } });
    expect(hasSurplus(chosen, 'add')).toBe(true);
    expect(hasSurplus(chosen, null)).toBe(false);
    expect(hasSurplus(base(), null)).toBe(false);
  });
});

describe('untouched', () => {
  it('lists publish and thumbnail only when the JSON did not change them', () => {
    expect(untouched(base())).toEqual(
      expect.arrayContaining(['nội dung đăng', 'ảnh bìa', 'ảnh', 'nhạc']),
    );
    const some = untouched(
      base({ diff: [{ scene_index: null, field: 'publish', before: {}, after: {} }] }),
    );
    expect(some).not.toContain('nội dung đăng');
    expect(some).toContain('ảnh bìa');
  });
});
