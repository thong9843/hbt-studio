import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import type { PostvProject } from '../api/types';
import { ArrowLeftIcon } from '../components/icons';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Chip } from '../components/ui/Chip';
import { IconButton } from '../components/ui/IconButton';
import { usePostvEditor } from '../hooks/postvEditor';
import { vi } from '../i18n/vi';
import { formatCount } from '../utils/count';
import {
  LONG_SECONDS,
  segmentSeconds,
  suggestByLikes,
  syncSegments,
  totalSeconds,
} from '../utils/postvSegments';

const withSegments = (p: PostvProject): PostvProject => ({ ...p, segments: syncSegments(p) });
const excerpt = (text: string, n = 70) => {
  const s = text.replace(/\s+/g, ' ').trim();
  return s.length > n ? `${s.slice(0, n).trimEnd()}…` : s;
};

/** Bước 2 · Chọn đoạn: chọn bình luận, đổi thứ tự, xem thời lượng ước tính (chỉ nhắc từ 120 s). */
export function PostvPickPage() {
  const { project, update, flush } = usePostvEditor();
  const navigate = useNavigate();
  const t = vi.postv.pick;
  const picked = project.comments.filter((c) => c.picked);

  // Vào bước này lần đầu: dựng sẵn danh sách đoạn từ phần đã chọn.
  useEffect(() => {
    if (project.segments.length === 0 && project.post.text.trim() !== '') {
      update(withSegments);
    }
    // chỉ khi mở màn
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggle = (id: string) =>
    update((p) =>
      withSegments({
        ...p,
        comments: p.comments.map((c) => (c.id === id ? { ...c, picked: !c.picked } : c)),
      }),
    );
  const move = (index: number, by: -1 | 1) =>
    update((p) => {
      const to = index + by;
      if (to < 0 || to >= p.comments.length) return p;
      const comments = [...p.comments];
      [comments[index], comments[to]] = [comments[to], comments[index]];
      return withSegments({ ...p, comments });
    });
  const suggest = () => update((p) => withSegments({ ...p, comments: suggestByLikes(p.comments) }));
  const clear = () =>
    update((p) =>
      withSegments({ ...p, comments: p.comments.map((c) => ({ ...c, picked: false })) }),
    );

  const handleOf = (ref: string | null) =>
    project.comments.find((c) => c.id === ref)?.handle || ref || '';
  const total = totalSeconds(project.segments);
  const cards = project.segments.filter((s) => s.card !== 'none' && s.card !== null).length;
  const long = total >= LONG_SECONDS;

  return (
    <div className="grid gap-4 min-[1024px]:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_300px]">
      <Card as="section" aria-label={t.listTitle} className="flex min-w-0 flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="mr-auto text-h2 font-bold">{t.listTitle}</h2>
          <span className="text-small text-muted">
            {t.selected(picked.length, project.comments.length)}
          </span>
          <Chip small disabled={project.comments.length === 0} onClick={suggest}>
            {t.suggest}
          </Chip>
          <Chip small disabled={picked.length === 0} onClick={clear}>
            {t.clear}
          </Chip>
        </div>

        <div className="ui-inner flex items-center gap-3 p-3">
          <input type="checkbox" checked disabled aria-label={t.postRow} className="h-5 w-5" />
          <div className="min-w-0 flex-1">
            <p className="text-small font-bold">
              {t.postRow} · {project.post.handle}
            </p>
            <p className="truncate text-small text-muted">{excerpt(project.post.text)}</p>
          </div>
          {project.post.likes !== null && (
            <span className="num text-small font-bold">♥ {formatCount(project.post.likes)}</span>
          )}
        </div>

        {project.comments.length === 0 && <p className="text-small text-muted">{t.noComments}</p>}
        <ul
          className="max-h-[520px] space-y-2 overflow-y-auto"
          aria-label={vi.postv.source.commentRole}
        >
          {project.comments.map((c, i) => (
            <li key={c.id} className="ui-inner flex items-center gap-3 p-3">
              <input
                type="checkbox"
                checked={c.picked}
                onChange={() => toggle(c.id)}
                aria-label={t.pickLabel(c.handle || c.id)}
                className="h-5 w-5"
              />
              <div className="min-w-0 flex-1">
                <p className="text-small font-bold">{c.handle || c.id}</p>
                <p className="truncate text-small text-muted">{excerpt(c.text)}</p>
              </div>
              {c.likes !== null && (
                <span className="num text-small font-bold">♥ {formatCount(c.likes)}</span>
              )}
              <div className="flex shrink-0">
                <IconButton
                  small
                  label={t.up(c.handle || c.id)}
                  disabled={i === 0}
                  onClick={() => move(i, -1)}
                >
                  <ArrowLeftIcon size={16} style={{ transform: 'rotate(90deg)' }} />
                </IconButton>
                <IconButton
                  small
                  label={t.down(c.handle || c.id)}
                  disabled={i === project.comments.length - 1}
                  onClick={() => move(i, 1)}
                >
                  <ArrowLeftIcon size={16} style={{ transform: 'rotate(-90deg)' }} />
                </IconButton>
              </div>
            </li>
          ))}
        </ul>
      </Card>

      <Card as="section" aria-label={t.orderTitle} className="flex min-w-0 flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-h2 font-bold">{t.orderTitle}</h2>
          <span className="text-small text-muted">{t.orderHint}</span>
        </div>
        <ol className="space-y-2">
          {project.segments.map((s, i) => (
            <li key={`${s.role}-${s.ref ?? i}`} className="ui-inner flex items-center gap-3 p-3">
              <span className="num flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-soft text-small font-bold">
                {i + 1}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-small font-bold">{t.roles[s.role]}</p>
                <p className="truncate text-small text-muted">
                  {s.role === 'comment'
                    ? handleOf(s.ref)
                    : s.role === 'post'
                      ? project.post.handle
                      : t.cards[s.card ?? 'none']}
                </p>
              </div>
              <span className="num text-small font-semibold">
                {s.voice.trim() ? `≈ ${Math.round(segmentSeconds(s))} s` : '—'}
              </span>
            </li>
          ))}
        </ol>
      </Card>

      <aside aria-label={t.total} className="flex flex-col gap-3">
        <Button
          tone="ink"
          size="lg"
          onClick={() => {
            void flush().then(() => navigate('../script'));
          }}
        >
          {vi.postv.next.script}
        </Button>
        <Card className="space-y-2">
          <div className="flex items-baseline justify-between">
            <span className="text-small font-semibold text-muted">{t.total}</span>
            <span className="num text-h2 font-extrabold">≈ {Math.round(total)} s</span>
          </div>
          <p className="text-small text-muted">{t.segments(project.segments.length, cards)}</p>
          {long ? (
            <Badge tone="yel">{t.longNow}</Badge>
          ) : (
            <p className="text-small text-muted">{t.long}</p>
          )}
        </Card>
      </aside>
    </div>
  );
}
