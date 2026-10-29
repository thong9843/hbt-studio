import type { PostvComment, PostvProject, PostvSegment } from '../api/types';

/** Tốc độ đọc VieNeu trên máy cũ: 16,5 ký tự/giây (đo PV0). Khớp `hbt/postv/script.py`. */
export const READ_CPS = 16.5;
/** Từ mức này trở lên chỉ nhắc (video dưới 2 phút). */
export const LONG_SECONDS = 120;

export const voiceChars = (text: string) => text.split(/\s+/).filter(Boolean).join(' ').length;

export const estimateSeconds = (chars: number) => Math.round((chars / READ_CPS) * 10) / 10;

export const segmentSeconds = (seg: PostvSegment) => estimateSeconds(voiceChars(seg.voice));

export const totalSeconds = (segments: PostvSegment[]) =>
  estimateSeconds(segments.reduce((sum, s) => sum + voiceChars(s.voice), 0));

/**
 * Dựng danh sách đoạn từ phần đã chọn: hook → bài gốc → các bình luận đã chọn (theo thứ tự) →
 * góc nhìn. Đoạn đã có (cùng vai trò và bình luận) giữ nguyên lời đã sửa.
 */
export function syncSegments(p: PostvProject): PostvSegment[] {
  const old = p.segments;
  const find = (role: PostvSegment['role'], ref: string | null) =>
    old.find((s) => s.role === role && (s.ref ?? null) === ref);
  const out: PostvSegment[] = [
    find('hook', null) ?? { role: 'hook', card: 'hook', voice: '', ref: null },
    find('post', null) ?? { role: 'post', card: 'post', voice: p.post.text.trim(), ref: null },
  ];
  for (const c of p.comments) {
    if (!c.picked) continue;
    out.push(
      find('comment', c.id) ?? {
        role: 'comment',
        card: 'comment',
        voice: c.text.trim(),
        ref: c.id,
      },
    );
  }
  const commentary = old.filter((s) => s.role === 'commentary');
  if (commentary.length === 0) {
    out.push({ role: 'commentary', card: 'none', voice: '', ref: null });
  } else {
    out.push(...commentary);
  }
  return out;
}

/** Bình luận có nhiều like nhất đứng trước; chưa ai có số like thì giữ thứ tự cũ. */
export function suggestByLikes(comments: PostvComment[], take = 3): PostvComment[] {
  const ranked = [...comments].sort((a, b) => (b.likes ?? 0) - (a.likes ?? 0));
  const top = new Set(ranked.slice(0, take).map((c) => c.id));
  return comments.map((c) => ({ ...c, picked: top.has(c.id) }));
}

/** Chữ trên thẻ bài gốc: `card_text` nếu có, không thì phần đầu của bài (tối đa ~160 ký tự). */
export function cardText(p: PostvProject['post'], limit = 160): string {
  if (p.card_text) return p.card_text;
  const text = p.text.trim().replace(/\s+/g, ' ');
  if (text.length <= limit) return text;
  const cut = text.slice(0, limit);
  const end = Math.max(cut.lastIndexOf('. '), cut.lastIndexOf('! '), cut.lastIndexOf('? '));
  const base = end > limit / 2 ? cut.slice(0, end + 1) : cut.slice(0, cut.lastIndexOf(' '));
  return `${base.trimEnd()}…`;
}

/** Id bình luận chưa dùng: c1, c2, … */
export function nextCommentId(comments: PostvComment[]): string {
  const used = new Set(comments.map((c) => c.id));
  for (let n = 1; ; n++) if (!used.has(`c${n}`)) return `c${n}`;
}
