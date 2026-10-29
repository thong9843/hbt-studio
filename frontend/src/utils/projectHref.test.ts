import { describe, expect, it } from 'vitest';
import { isPostv, type AnyProject } from '../api/types';
import { projectHref } from './projectHref';

describe('projectHref', () => {
  it('opens PostV on its own screen and everything else in the scene editor', () => {
    expect(projectHref({ slug: 'a', kind: 'postv' })).toBe('/postv/a');
    expect(projectHref({ slug: 'a', kind: 'video' })).toBe('/p/a');
    expect(projectHref({ slug: 'a' })).toBe('/p/a'); // dự án cũ / bản tóm tắt chưa có `kind`
  });
});

describe('isPostv', () => {
  it('tells the two project types apart by `kind`', () => {
    const video = { slug: 'a', scenes: [] } as unknown as AnyProject;
    const postv = { kind: 'postv', slug: 'b' } as unknown as AnyProject;
    expect(isPostv(video)).toBe(false);
    expect(isPostv(postv)).toBe(true);
  });
});
