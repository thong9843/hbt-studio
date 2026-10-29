import { describe, expect, it } from 'vitest';
import type { PostvComment, PostvProject } from '../api/types';
import {
  LONG_SECONDS,
  READ_CPS,
  cardText,
  estimateSeconds,
  nextCommentId,
  suggestByLikes,
  syncSegments,
  totalSeconds,
  voiceChars,
} from './postvSegments';

const stats = { views: null, likes: null, replies: null, reposts: null, shares: null };
const comment = (id: string, over: Partial<PostvComment> = {}): PostvComment => ({
  id,
  handle: `user_${id}`,
  age: '1 giờ',
  text: `Bình luận ${id}`,
  parent: null,
  picked: false,
  ...stats,
  ...over,
});
const project = (over: Partial<PostvProject> = {}): PostvProject =>
  ({
    version: 1,
    kind: 'postv',
    slug: 'a',
    title: 'A',
    post: { handle: 'tac_gia', age: '17 giờ', text: 'Bài gốc', card_text: null, ...stats },
    comments: [],
    segments: [],
    ...over,
  }) as PostvProject;

describe('reading speed (matches backend script.py)', () => {
  it('uses 16.5 characters per second and a 120 s reminder', () => {
    expect(READ_CPS).toBe(16.5);
    expect(LONG_SECONDS).toBe(120);
    expect(estimateSeconds(165)).toBe(10);
    expect(voiceChars('  Xin   chào \n bạn ')).toBe('Xin chào bạn'.length);
  });

  it('sums the voice of every segment', () => {
    const segs = [
      { role: 'post', card: 'post', voice: 'a'.repeat(33), ref: null },
      { role: 'commentary', card: 'none', voice: 'b'.repeat(66), ref: null },
    ] as PostvProject['segments'];
    expect(totalSeconds(segs)).toBe(6);
  });
});

describe('syncSegments', () => {
  it('builds hook, post, picked comments in order, then commentary', () => {
    const p = project({
      comments: [comment('c1', { picked: true }), comment('c2'), comment('c3', { picked: true })],
    });
    const segs = syncSegments(p);
    expect(segs.map((s) => [s.role, s.ref, s.card])).toEqual([
      ['hook', null, 'hook'],
      ['post', null, 'post'],
      ['comment', 'c1', 'comment'],
      ['comment', 'c3', 'comment'],
      ['commentary', null, 'none'],
    ]);
    expect(segs[1].voice).toBe('Bài gốc');
    expect(segs[2].voice).toBe('Bình luận c1');
  });

  it('keeps voice text the user already edited and drops unselected comments', () => {
    const p = project({
      comments: [comment('c1', { picked: true }), comment('c2', { picked: true })],
    });
    const first = syncSegments(p);
    first[2].voice = 'Một bạn nói quán ở đâu vậy';
    const edited = { ...p, segments: first };
    const unpicked = {
      ...edited,
      comments: [edited.comments[0], { ...edited.comments[1], picked: false }],
    };
    const again = syncSegments(unpicked);
    expect(again.find((s) => s.ref === 'c1')?.voice).toBe('Một bạn nói quán ở đâu vậy');
    expect(again.some((s) => s.ref === 'c2')).toBe(false);
  });

  it('keeps every commentary segment the user added', () => {
    const p = project({
      segments: [
        { role: 'commentary', card: 'none', voice: 'Một', ref: null },
        { role: 'commentary', card: 'none', voice: 'Hai', ref: null },
      ],
    });
    expect(
      syncSegments(p)
        .filter((s) => s.role === 'commentary')
        .map((s) => s.voice),
    ).toEqual(['Một', 'Hai']);
  });
});

describe('suggestByLikes', () => {
  it('picks the three most liked comments and keeps the list order', () => {
    const list = [
      comment('c1', { likes: 5 }),
      comment('c2', { likes: 900 }),
      comment('c3', { likes: 20 }),
      comment('c4', { likes: 1200 }),
      comment('c5', { likes: 1 }),
    ];
    const res = suggestByLikes(list);
    expect(res.map((c) => c.id)).toEqual(['c1', 'c2', 'c3', 'c4', 'c5']);
    expect(res.filter((c) => c.picked).map((c) => c.id)).toEqual(['c2', 'c3', 'c4']);
  });

  it('falls back to the first three when nobody has likes', () => {
    const res = suggestByLikes([comment('c1'), comment('c2'), comment('c3'), comment('c4')]);
    expect(res.map((c) => c.picked)).toEqual([true, true, true, false]);
  });
});

describe('cardText / nextCommentId', () => {
  it('uses card_text, otherwise the start of the post cut at a sentence', () => {
    expect(cardText({ ...project().post, card_text: 'Tiêu đề' })).toBe('Tiêu đề');
    const long = `${'Câu một dài dài. '.repeat(3)}${'x'.repeat(200)}`;
    const text = cardText({ ...project().post, text: long });
    expect(text.endsWith('…') || text.endsWith('.')).toBe(true);
    expect(text.length).toBeLessThanOrEqual(161);
    expect(cardText({ ...project().post, text: 'Ngắn' })).toBe('Ngắn');
  });

  it('finds an unused comment id', () => {
    expect(nextCommentId([])).toBe('c1');
    expect(nextCommentId([comment('c1'), comment('c3')])).toBe('c2');
  });
});
