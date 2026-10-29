import { keepPreviousData, useMutation, useQuery } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/endpoints';
import type { PostvComment, PostvParseResult, PostvProject } from '../api/types';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { ErrorNote } from '../components/ErrorNote';
import { AlertIcon, MoreIcon, PlusIcon, UploadIcon } from '../components/icons';
import { PostvCardPreview } from '../components/postv/PostvCardPreview';
import { StatInput } from '../components/postv/StatInput';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Chip } from '../components/ui/Chip';
import { Input, Textarea } from '../components/ui/Field';
import { Menu } from '../components/ui/Menu';
import { usePostvEditor } from '../hooks/postvEditor';
import { vi } from '../i18n/vi';
import { nextCommentId, syncSegments } from '../utils/postvSegments';

const NO_STATS = { views: null, likes: null, replies: null, reposts: null, shares: null };
const isHttp = (url: string) => /^https?:\/\/\S+$/i.test(url.trim());

/** Giữ danh sách đoạn khớp với bình luận khi đã có đoạn (chưa có thì để bước Chọn đoạn tạo). */
function withSegments(p: PostvProject): PostvProject {
  return p.segments.length > 0 ? { ...p, segments: syncSegments(p) } : p;
}

type Stat = keyof typeof NO_STATS;

/** Bước 1 · Nhập nguồn: dán chữ, tách bài + bình luận, sửa tay, nhập số liệu (IMPLEMENT-POSTV §7). */
export function PostvSourcePage() {
  const { project, update, flush, savedCount } = usePostvEditor();
  const navigate = useNavigate();
  const t = vi.postv.source;
  const [raw, setRaw] = useState('');
  const [notice, setNotice] = useState<string[]>([]);
  const [hints, setHints] = useState<PostvParseResult['hints']>([]);
  const [pending, setPending] = useState<PostvParseResult | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const check = useQuery({
    queryKey: ['postv-check', project.slug, savedCount],
    queryFn: () => api.postvCheck(project.slug),
    placeholderData: keepPreviousData,
    retry: false,
  });

  const hasSource = project.post.text.trim() !== '' || project.comments.length > 0;

  function apply(res: PostvParseResult) {
    const post = res.post;
    if (!post) return;
    update((p) => ({
      ...p,
      source: {
        ...p.source,
        url: res.source_url ?? p.source.url,
        pasted_at: new Date().toISOString(),
      },
      post: { ...p.post, handle: post.handle, age: post.age, text: post.text, card_text: null },
      comments: res.comments.map((c) => ({
        id: c.id,
        handle: c.handle,
        age: c.age,
        text: c.text,
        parent: null,
        picked: c.picked,
        ...NO_STATS,
      })),
      segments: [], // nguồn mới: đoạn cũ không còn khớp, bước Chọn đoạn dựng lại
    }));
    setHints(res.hints);
    setPending(null);
  }

  const parse = useMutation({
    mutationFn: (text: string) => api.parsePostv(text),
    onSuccess: (res) => {
      setNotice(res.warnings);
      if (res.guess === 'embed') {
        const url = res.source_url;
        if (url && !project.source.url) update((p) => ({ ...p, source: { ...p.source, url } }));
        return;
      }
      if (res.guess !== 'threads_text' || !res.post) {
        if (res.warnings.length === 0) setNotice([t.unknown]);
        return;
      }
      if (hasSource) setPending(res);
      else apply(res);
    },
  });

  async function pickFile(file: File | undefined) {
    if (!file) return;
    setFileError(null);
    try {
      setRaw(await file.text());
    } catch {
      setFileError(t.fileFailed);
    }
  }

  const setPost = (patch: Partial<PostvProject['post']>) =>
    update((p) => ({ ...p, post: { ...p.post, ...patch } }));
  const setComment = (id: string, patch: Partial<PostvComment>) =>
    update((p) => ({
      ...p,
      comments: p.comments.map((c) => (c.id === id ? { ...c, ...patch } : c)),
    }));
  const removeComment = (id: string) =>
    update((p) => withSegments({ ...p, comments: p.comments.filter((c) => c.id !== id) }));
  const addComment = () =>
    update((p) =>
      withSegments({
        ...p,
        comments: [
          ...p.comments,
          {
            id: nextCommentId(p.comments),
            handle: '',
            age: '',
            text: '',
            parent: null,
            picked: false,
            ...NO_STATS,
          },
        ],
      }),
    );
  const makePost = (id: string) =>
    update((p) => {
      const target = p.comments.find((c) => c.id === id);
      if (!target) return p;
      const demoted: PostvComment = {
        id: nextCommentId(p.comments),
        handle: p.post.handle,
        age: p.post.age,
        text: p.post.text,
        parent: null,
        picked: false,
        views: p.post.views,
        likes: p.post.likes,
        replies: p.post.replies,
        reposts: p.post.reposts,
        shares: p.post.shares,
      };
      return {
        ...p,
        post: {
          handle: target.handle,
          age: target.age,
          text: target.text,
          card_text: null,
          views: target.views,
          likes: target.likes,
          replies: target.replies,
          reposts: target.reposts,
          shares: target.shares,
        },
        comments: p.comments.map((c) => (c.id === id ? demoted : c)),
        segments: [],
      };
    });

  const applyHint = (index: number, yes: boolean) => {
    const hint = hints[index];
    if (yes && hint.value !== null) {
      if (hint.block === 0) setPost({ likes: hint.value });
      else {
        const target = project.comments[hint.block - 1];
        if (target) setComment(target.id, { likes: hint.value });
      }
    }
    setHints((h) => h.filter((_, i) => i !== index));
  };
  const hintWho = (block: number) =>
    block === 0 ? t.postRole : (project.comments[block - 1]?.handle ?? t.commentRole);

  const issues = check.data?.issues ?? [];
  const reminders = issues.filter((i) => i.level === 'warn').length;
  const needPost = project.post.text.trim() === '';
  const statFields: { key: Stat; required?: boolean }[] = [
    { key: 'likes', required: true },
    { key: 'replies', required: true },
    { key: 'shares', required: true },
    { key: 'reposts' },
    { key: 'views' },
  ];

  return (
    <div className="grid gap-4 min-[1024px]:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)_300px]">
      {/* Cột 1: dán chữ */}
      <Card as="section" aria-label={t.paste} className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-h2 font-bold">{t.paste}</h2>
          <span className="text-small text-muted">{t.pasteHint}</span>
        </div>
        <Textarea
          label={t.pasteLabel}
          rows={12}
          spellCheck={false}
          placeholder={t.pastePlaceholder}
          value={raw}
          onChange={(e) => setRaw(e.target.value)}
        />
        <div className="flex flex-wrap items-center gap-2">
          <Button
            tone="ghost"
            busy={parse.isPending}
            disabled={raw.trim() === ''}
            onClick={() => parse.mutate(raw)}
          >
            {t.split}
          </Button>
          <Button tone="soft" icon={<UploadIcon />} onClick={() => fileRef.current?.click()}>
            {t.pickFile}
          </Button>
          <input
            ref={fileRef}
            type="file"
            accept=".txt,.md,text/plain,text/markdown"
            className="sr-only"
            tabIndex={-1}
            aria-label={t.pickFile}
            onChange={(e) => {
              void pickFile(e.target.files?.[0]);
              e.target.value = '';
            }}
          />
        </div>
        {fileError && <p className="text-small text-danger">{fileError}</p>}
        <ErrorNote error={parse.error} />
        {notice.length > 0 && (
          <ul className="ui-inner space-y-1 p-3" aria-label={t.result}>
            {notice.map((n) => (
              <li key={n} className="flex items-start gap-2 text-small font-semibold">
                <AlertIcon size={16} />
                {n}
              </li>
            ))}
          </ul>
        )}
        <div className="flex items-end gap-2">
          <div className="min-w-0 flex-1">
            <Input
              label={t.link}
              placeholder={t.linkPlaceholder}
              value={project.source.url}
              onChange={(e) =>
                update((p) => ({ ...p, source: { ...p.source, url: e.target.value } }))
              }
            />
          </div>
          {isHttp(project.source.url) ? (
            <a
              href={project.source.url.trim()}
              target="_blank"
              rel="noopener noreferrer"
              className="ui-btn ui-btn-soft"
            >
              {t.openPost}
            </a>
          ) : (
            <Button tone="soft" disabled>
              {t.openPost}
            </Button>
          )}
        </div>
      </Card>

      {/* Cột 2: kết quả tách, sửa tay */}
      <Card as="section" aria-label={t.result} className="flex min-w-0 flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-h2 font-bold">{t.result}</h2>
          <span className="text-small text-muted">{t.counts(project.comments.length)}</span>
        </div>

        {hints.map((h, i) => (
          <div
            key={`${h.block}-${h.raw}`}
            role="group"
            aria-label={t.hint(h.raw, hintWho(h.block))}
            className="ui-inner flex flex-wrap items-center gap-2 p-3"
          >
            <AlertIcon size={16} />
            <span className="min-w-0 flex-1 text-small font-semibold">
              {t.hint(h.raw, hintWho(h.block))}
            </span>
            <Chip small disabled={h.value === null} onClick={() => applyHint(i, true)}>
              {t.hintYes}
            </Chip>
            <Chip small onClick={() => applyHint(i, false)}>
              {t.hintNo}
            </Chip>
          </div>
        ))}

        <div className="ui-inner space-y-3 p-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-small font-bold">{t.postRole}</span>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            <Input
              label={t.handle}
              value={project.post.handle}
              onChange={(e) => setPost({ handle: e.target.value })}
            />
            <Input
              label={t.age}
              value={project.post.age}
              onChange={(e) => setPost({ age: e.target.value })}
            />
          </div>
          <Textarea
            label={t.text}
            rows={4}
            value={project.post.text}
            onChange={(e) => setPost({ text: e.target.value })}
          />
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
            {statFields.map(({ key, required }) => (
              <StatInput
                key={key}
                label={t.stats[key]}
                required={required}
                value={project.post[key]}
                onChange={(v) => setPost({ [key]: v } as Partial<PostvProject['post']>)}
              />
            ))}
          </div>
        </div>

        {project.comments.length === 0 && <p className="text-small text-muted">{t.empty}</p>}
        <ul className="max-h-[420px] space-y-2 overflow-y-auto" aria-label={t.commentRole}>
          {project.comments.map((c) => (
            <li key={c.id} className="ui-inner space-y-2 p-3">
              <div className="flex items-center gap-2">
                <div className="grid min-w-0 flex-1 grid-cols-2 gap-2">
                  <Input
                    aria-label={`${t.handle} ${c.id}`}
                    placeholder={t.handle}
                    value={c.handle}
                    onChange={(e) => setComment(c.id, { handle: e.target.value })}
                  />
                  <Input
                    aria-label={`${t.age} ${c.id}`}
                    placeholder={t.age}
                    value={c.age}
                    onChange={(e) => setComment(c.id, { age: e.target.value })}
                  />
                </div>
                <div className="w-[76px] shrink-0">
                  <StatInput
                    compact
                    label={t.stats.likes}
                    ariaLabel={t.likesOf(c.handle || c.id)}
                    value={c.likes}
                    onChange={(v) => setComment(c.id, { likes: v })}
                  />
                </div>
                <Menu
                  label={t.menu(c.handle)}
                  icon={<MoreIcon />}
                  items={[
                    { key: 'post', label: t.makePost, onSelect: () => makePost(c.id) },
                    {
                      key: 'remove',
                      label: t.remove,
                      danger: true,
                      onSelect: () => removeComment(c.id),
                    },
                  ]}
                />
              </div>
              <Textarea
                aria-label={`${t.text} ${c.id}`}
                rows={2}
                value={c.text}
                onChange={(e) => setComment(c.id, { text: e.target.value })}
              />
            </li>
          ))}
        </ul>
        <div>
          <Button tone="soft" icon={<PlusIcon />} onClick={addComment}>
            {t.addComment}
          </Button>
        </div>
      </Card>

      {/* Cột 3: nút chính + xem trước thẻ */}
      <aside aria-label={t.previewTitle} className="flex flex-col gap-3">
        <Button
          tone="ink"
          size="lg"
          disabled={needPost}
          title={needPost ? vi.postv.needPost : undefined}
          onClick={() => {
            void flush().then(() => navigate('pick'));
          }}
        >
          {vi.postv.next.pick}
        </Button>
        <p className="text-center text-small font-semibold text-muted">
          {check.data
            ? [
                check.data.censored > 0 ? t.censored(check.data.censored) : t.cleanSource,
                reminders > 0 ? t.reminders(reminders) : null,
              ]
                .filter(Boolean)
                .join(' · ')
            : ' '}
        </p>
        <PostvCardPreview post={project.post} />
      </aside>

      {pending && (
        <ConfirmDialog
          title={t.replaceTitle}
          message={t.replaceMessage}
          confirmLabel={t.replace}
          onConfirm={() => apply(pending)}
          onCancel={() => setPending(null)}
        />
      )}
    </div>
  );
}
