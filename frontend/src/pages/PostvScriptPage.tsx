import { Link, useNavigate } from 'react-router-dom';
import { PostvMusicCard } from '../components/postv/PostvMusicCard';
import { PostvVoiceCard } from '../components/postv/PostvVoiceCard';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Textarea } from '../components/ui/Field';
import { usePostvEditor } from '../hooks/postvEditor';
import { vi } from '../i18n/vi';
import { segmentSeconds, totalSeconds, voiceChars } from '../utils/postvSegments';

/** Ai đọc đoạn: ghi tay thì theo đó; còn lại bài gốc → bài gốc, bình luận → tài khoản, khác → người dẫn. */
function readerOf(role: string, ref: string | null, speaker: string | null | undefined): string {
  if (speaker) return speaker;
  if (role === 'post') return 'post';
  if (role === 'comment' && ref) return ref;
  return 'narrator';
}

/** Bước 3 · Kịch bản và giọng: lời đọc từng đoạn, thẻ Giọng, thẻ Nhạc. */
export function PostvScriptPage() {
  const { project, update, flush } = usePostvEditor();
  const navigate = useNavigate();
  const t = vi.postv.script;
  const roles = vi.postv.pick.roles;
  const V = vi.postv.voice;

  const nameOf = (who: string) =>
    who === 'narrator'
      ? V.narrator
      : who === 'post'
        ? project.post.handle || V.post
        : project.comments.find((c) => c.id === who)?.handle || who;
  const setText = (i: number, voice: string) =>
    update((p) => ({
      ...p,
      segments: p.segments.map((s, k) => (k === i ? { ...s, voice } : s)),
    }));
  const total = totalSeconds(project.segments);
  const empty = project.segments.filter((s) => s.role !== 'commentary' && !s.voice.trim()).length;

  return (
    <div className="grid gap-4 min-[1024px]:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_300px]">
      <Card as="section" aria-label={t.listTitle} className="flex min-w-0 flex-col gap-3">
        <div>
          <h2 className="text-h2 font-bold">{t.listTitle}</h2>
          <p className="text-small text-muted">{t.lead}</p>
        </div>
        {project.segments.length === 0 && (
          <div className="ui-inner flex flex-wrap items-center gap-3 p-3">
            <p className="min-w-0 flex-1 text-small font-semibold">{t.empty}</p>
            <Link to="../pick" className="ui-btn ui-btn-soft ui-btn-sm">
              {t.back}
            </Link>
          </div>
        )}
        <ol className="space-y-3">
          {project.segments.map((s, i) => {
            const who = readerOf(s.role, s.ref, s.speaker);
            const role = roles[s.role];
            return (
              <li key={`${s.role}-${s.ref ?? i}`} className="space-y-1">
                <div className="flex items-center gap-2 text-small">
                  <span className="num flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-soft font-bold">
                    {i + 1}
                  </span>
                  <span className="font-bold">{role}</span>
                  <span className="min-w-0 flex-1 truncate text-muted">
                    {t.reader(nameOf(who))}
                  </span>
                  <span className="num text-muted">
                    {t.chars(voiceChars(s.voice))} ·{' '}
                    {s.voice.trim() ? t.seconds(segmentSeconds(s)) : '—'}
                  </span>
                </div>
                <Textarea
                  aria-label={t.segmentLabel(i + 1, role)}
                  rows={s.role === 'comment' || s.role === 'post' ? 3 : 2}
                  placeholder={s.role === 'commentary' ? t.commentaryNote : t.placeholder}
                  value={s.voice}
                  onChange={(e) => setText(i, e.target.value)}
                />
              </li>
            );
          })}
        </ol>
      </Card>

      <div className="flex min-w-0 flex-col gap-4">
        <PostvVoiceCard />
        <PostvMusicCard />
      </div>

      <aside aria-label={t.total} className="flex flex-col gap-3">
        <Button
          tone="ink"
          size="lg"
          onClick={() => {
            void flush().then(() => navigate('../preview'));
          }}
        >
          {t.next}
        </Button>
        <Card className="space-y-2">
          <div className="flex items-baseline justify-between">
            <span className="text-small font-semibold text-muted">{t.total}</span>
            <span className="num text-h2 font-extrabold">≈ {Math.round(total)} s</span>
          </div>
          {empty > 0 && <Badge tone="yel">{t.missingText}</Badge>}
        </Card>
      </aside>
    </div>
  );
}
