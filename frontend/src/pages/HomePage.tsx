import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { fetchHealth } from '../api/client';
import { api } from '../api/endpoints';
import type { ProjectSummary, RenderSummary, UnifiedRenderItem } from '../api/types';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { EmptyProjects } from '../components/EmptyProjects';
import { ErrorNote } from '../components/ErrorNote';
import {
  CheckIcon,
  MessagesSquareIcon,
  MoreIcon,
  PlayIcon,
  SmartphoneIcon,
  ZapIcon,
} from '../components/icons';
import { CardImage } from '../components/ProjectCard';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Dialog } from '../components/ui/Dialog';
import { Menu } from '../components/ui/Menu';
import { Skeleton } from '../components/ui/Skeleton';
import { useNewProject } from '../hooks/newProject';
import { useToast } from '../hooks/toast';
import { vi } from '../i18n/vi';
import { formatDate, formatDuration } from '../utils/format';
import { projectHref } from '../utils/projectHref';
import { projectImage, projectStatus } from '../utils/projectStatus';
import { latestExport, readiness } from '../utils/readiness';

const RECENT = 4;
const TONE = { final: 'red', preview: 'yel', none: 'neutral', broken: 'danger' } as const;

const ENGINE_LABELS: Record<'all' | 'core' | 'postv' | 'chatting', string> = {
  all: 'Tất cả',
  core: 'HBT Core',
  postv: 'PostV',
  chatting: 'Chatting',
};

const ENGINE_BADGE_STYLE: Record<'core' | 'postv' | 'chatting', string> = {
  core: 'bg-[#D9232E] text-white border-[#F87171]/40',
  postv: 'bg-white text-[#0B0D12] border-white/80',
  chatting: 'bg-[#FACC15] text-[#0B0D12] border-[#FACC15]',
};

function Dot({ on, label }: { on: boolean; label: string }) {
  const t = vi.home.dot;
  return (
    <li className="flex items-center gap-1.5 text-small font-semibold">
      <span
        aria-hidden="true"
        className={
          on
            ? 'flex h-5 w-5 items-center justify-center rounded-full bg-ok text-white'
            : 'h-5 w-5 rounded-full border-2 border-line-input'
        }
      >
        {on && <CheckIcon size={12} strokeWidth={3} />}
      </span>
      <span>{label}</span>
      <span className="sr-only">{on ? t.yes : t.no}</span>
    </li>
  );
}

/** Thẻ "Tiếp tục làm": dự án sửa gần nhất. Chấm nguyên liệu lấy bằng một lần GET project, không poll. */
function Continue({
  project,
  onDelete,
}: {
  project: ProjectSummary;
  onDelete: (p: ProjectSummary) => void;
}) {
  const t = vi.home;
  const status = projectStatus(project);
  const brief = useQuery({
    queryKey: ['project-brief', project.slug],
    queryFn: () => api.getProject(project.slug),
    enabled: project.kind !== 'postv', // PostV chưa có chấm nguyên liệu (PV6)
  });
  const ready = brief.data ? readiness(brief.data) : null;
  const series = brief.data?.series;
  const video = project.last_final?.video ?? project.last_render?.video ?? null;
  return (
    <Card as="section" aria-label={t.continue} className="flex gap-6">
      <div className="aspect-[9/16] w-[132px] shrink-0 overflow-hidden rounded-inner bg-soft">
        <CardImage src={projectImage(project)} />
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-3">
        <p className="text-tiny font-semibold text-muted">{t.continue}</p>
        <h2 className="line-clamp-2 text-title font-extrabold">{project.title}</h2>
        <div className="flex flex-wrap items-center gap-2">
          {project.kind === 'postv' && <Badge>{vi.postv.badge}</Badge>}
          <Badge tone={TONE[status.kind]}>{status.label}</Badge>
          {series && <span className="text-small text-muted">{series}</span>}
        </div>
        {ready ? (
          <ul className="flex flex-wrap gap-x-4 gap-y-2" aria-label={t.dot.label}>
            <Dot
              on={ready.images.total > 0 && ready.images.done === ready.images.total}
              label={t.dot.images(ready.images.done, ready.images.total)}
            />
            <Dot on={ready.voice} label={t.dot.voice} />
            <Dot on={ready.music} label={t.dot.music} />
            <Dot on={ready.cover} label={t.dot.cover} />
          </ul>
        ) : (
          project.kind !== 'postv' && !brief.isError && <Skeleton width={260} height={20} />
        )}
        <div className="mt-auto flex flex-wrap items-center gap-2 pt-2">
          <Link to={projectHref(project)} className="ui-btn ui-btn-ink">
            {t.open}
          </Link>
          {video && (
            <a
              href={video}
              target="_blank"
              rel="noreferrer"
              className="ui-btn ui-btn-soft"
              aria-label={`${t.watch}: ${project.title}`}
            >
              <PlayIcon size={18} />
              {t.watch}
            </a>
          )}
          <Menu
            label={vi.projects.menu(project.title)}
            icon={<MoreIcon />}
            items={[
              {
                key: 'delete',
                label: vi.projects.delete,
                danger: true,
                onSelect: () => onDelete(project),
              },
            ]}
          />
        </div>
      </div>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="py-1">
      <dt className="text-tiny font-semibold opacity-80">{label}</dt>
      <dd className="num mt-1 text-h2 font-bold">{value}</dd>
    </div>
  );
}

/** Thẻ tối "Lần xuất gần nhất": số liệu lấy từ `last_final`/`last_render`, không gọi thêm /renders. */
function LastExport({ project, render }: { project: ProjectSummary; render: RenderSummary }) {
  const t = vi.home.last;
  return (
    <section
      aria-label={t.title}
      className="flex flex-col gap-4 rounded-card border border-[var(--card-border)] bg-hero p-6 text-on-hero"
    >
      <p className="text-tiny font-semibold opacity-80">{vi.home.lastExport}</p>
      <h2 className="line-clamp-2 text-title font-extrabold">{project.title}</h2>
      <dl className="grid grid-cols-3 gap-2">
        <Stat label={t.fps} value={render.fps ? `${render.fps}` : '—'} />
        <Stat label={t.duration} value={render.duration ? formatDuration(render.duration) : '—'} />
        <Stat
          label={t.renderTime}
          value={render.render_seconds ? formatDuration(render.render_seconds) : '—'}
        />
      </dl>
      <p className="text-small opacity-80">
        {render.preview ? t.preview : t.final} ·{' '}
        <span className="num">{formatDate(render.created_at)}</span>
      </p>
      {render.video && (
        <a
          href={render.video}
          target="_blank"
          rel="noreferrer"
          className="ui-btn ui-btn-accent mt-auto self-start"
          aria-label={`${vi.home.watch}: ${project.title}`}
        >
          <PlayIcon size={18} />
          {vi.home.watch}
        </a>
      )}
    </section>
  );
}

function RecentCard({
  project,
  onDelete,
}: {
  project: ProjectSummary;
  onDelete: (p: ProjectSummary) => void;
}) {
  const status = projectStatus(project);
  const href = projectHref(project);
  return (
    <Card as="li" padded={false} className="ui-card-link">
      <Link to={href} aria-label={`${vi.projects.open}: ${project.title}`} className="block">
        <div className="aspect-[9/16] w-full overflow-hidden rounded-t-card bg-soft">
          <CardImage src={projectImage(project)} />
        </div>
      </Link>
      <div className="flex items-start justify-between gap-2 p-3">
        <div className="min-w-0 flex-1 space-y-2">
          <p className="line-clamp-2 text-small font-bold">
            <Link to={href} className="hover:underline">
              {project.title}
            </Link>
          </p>
          <div className="flex flex-wrap items-center gap-1.5">
            {project.kind === 'postv' && <Badge>{vi.postv.badge}</Badge>}
            <Badge tone={TONE[status.kind]}>{status.label}</Badge>
          </div>
        </div>
        <Menu
          label={vi.projects.menu(project.title)}
          icon={<MoreIcon />}
          items={[
            {
              key: 'delete',
              label: vi.projects.delete,
              danger: true,
              onSelect: () => onDelete(project),
            },
          ]}
        />
      </div>
    </Card>
  );
}

function HomeSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true">
      <div className="grid grid-cols-1 gap-6 min-[1024px]:grid-cols-[3fr_2fr]">
        <Skeleton height={236} className="!rounded-card" />
        <Skeleton height={236} className="!rounded-card" />
      </div>
    </div>
  );
}

export function HomePage() {
  const t = vi.home;
  const { open: openNew } = useNewProject();
  const [deleting, setDeleting] = useState<ProjectSummary | null>(null);
  const [engineFilter, setEngineFilter] = useState<'all' | 'core' | 'postv' | 'chatting'>('all');
  const [activeRender, setActiveRender] = useState<UnifiedRenderItem | null>(null);
  const [deletingRender, setDeletingRender] = useState<UnifiedRenderItem | null>(null);
  const queryClient = useQueryClient();
  const toast = useToast();

  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: () => fetchHealth(),
    retry: false,
  });

  const { data: coreAssets } = useQuery({
    queryKey: ['hbt-core-assets', ''],
    queryFn: () => api.getHbtCoreAssets(),
    retry: false,
  });

  const { data, isPending, error, refetch } = useQuery({
    queryKey: ['projects'],
    queryFn: api.listProjects,
  });

  const rendersQuery = useQuery({
    queryKey: ['unified-renders'],
    queryFn: () => api.listUnifiedRenders(),
    retry: false,
  });

  const remove = useMutation({
    mutationFn: (slug: string) => api.deleteProject(slug),
    onSuccess: () => {
      setDeleting(null);
      void queryClient.invalidateQueries({ queryKey: ['projects'] });
      toast.info(vi.projects.deleted);
    },
    onError: (err: Error) => {
      setDeleting(null);
      toast.error(err);
    },
  });

  const deleteRenderMut = useMutation({
    mutationFn: (item: UnifiedRenderItem) => api.deleteUnifiedRender(item.id),
    onSuccess: (_res, item) => {
      void queryClient.invalidateQueries({ queryKey: ['unified-renders'] });
      toast.info(`Đã xóa video "${item.title}"`);
      if (activeRender?.id === item.id) setActiveRender(null);
      setDeletingRender(null);
    },
    onError: (err: Error) => {
      toast.error(err);
      setDeletingRender(null);
    },
  });

  const latest = data?.[0];
  const recent = data?.slice(1, 1 + RECENT) ?? [];
  const last = data ? latestExport(data) : null;

  const allRenders = rendersQuery.data?.items ?? [];
  const filteredRenders =
    engineFilter === 'all' ? allRenders : allRenders.filter((r) => r.engine === engineFilter);

  const handleCopyPublishText = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      toast.info('Đã sao chép nội dung đăng bài!');
    } catch (err) {
      toast.error(err);
    }
  };

  return (
    <main className="mx-auto max-w-[1160px] space-y-6">
      {/* HBT Signature Hero Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-card border border-white/10 bg-[#131720] p-6">
        <div className="space-y-1">
          <div className="inline-flex items-center gap-2 rounded-pill border border-[#D9232E]/40 bg-[#D9232E]/15 px-3 py-0.5 text-tiny font-bold tracking-wider text-[#FACC15] uppercase">
            <span>HBT Signature Studio v4.0</span>
            <span className="text-white/40">•</span>
            <span className="text-white">9:16 TikTok / Reels / Shorts</span>
          </div>
          <h1 className="text-h1 font-extrabold">{t.title}</h1>
        </div>
        <div
          aria-label="Trạng thái môi trường"
          className="flex flex-wrap items-center gap-3 rounded-pill border border-line bg-card px-3.5 py-1.5 text-tiny font-semibold text-muted"
        >
          <span className="flex items-center gap-1.5">
            <span
              className={`h-2 w-2 rounded-full ${health?.vieneu ? 'bg-ok' : 'bg-muted'}`}
              aria-hidden="true"
            />
            VieNeu-TTS
          </span>
          <span className="text-line">·</span>
          <span className="flex items-center gap-1.5">
            <span
              className={`h-2 w-2 rounded-full ${coreAssets?.gemini_configured ? 'bg-ok' : 'bg-muted'}`}
              aria-hidden="true"
            />
            Gemini
          </span>
          <span className="text-line">·</span>
          <span className="flex items-center gap-1.5">
            <span
              className={`h-2 w-2 rounded-full ${health?.ffmpeg ? 'bg-ok' : 'bg-muted'}`}
              aria-hidden="true"
            />
            FFmpeg
          </span>
        </div>
      </div>

      {/* Lối tắt tạo video nhanh (3 Động cơ Studio — HBT Signature Bento Cards) */}
      <section aria-label={t.hub.title} className="grid grid-cols-1 gap-4 min-[900px]:grid-cols-3">
        {/* 1. HBT Core — Đỏ · Đen */}
        <Card className="flex flex-col justify-between gap-4 border-[#D9232E]/40 bg-[#131720] p-5">
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="flex h-8 w-8 items-center justify-center rounded-inner bg-[#D9232E] text-white">
                  <ZapIcon size={18} />
                </span>
                <h2 className="text-body font-extrabold">{t.hub.hbtCoreTitle}</h2>
              </div>
              <span className="rounded-pill bg-[#D9232E]/20 px-2.5 py-0.5 text-tiny font-bold text-[#FACC15]">
                9:16 Fill
              </span>
            </div>
            <p className="text-small text-muted">{t.hub.hbtCoreDesc}</p>
          </div>
          <Link to="/core" className="ui-btn ui-btn-brand ui-btn-sm self-start">
            {t.hub.hbtCoreCta}
          </Link>
        </Card>

        {/* 2. PostV — Trắng · Đỏ · Đen */}
        <Card className="flex flex-col justify-between gap-4 border-white/25 bg-[#131720] p-5">
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="flex h-8 w-8 items-center justify-center rounded-inner bg-white text-[#0B0D12]">
                  <SmartphoneIcon size={18} />
                </span>
                <h2 className="text-body font-extrabold">{t.hub.postvTitle}</h2>
              </div>
              <span className="rounded-pill bg-white/15 px-2.5 py-0.5 text-tiny font-bold text-white">
                9:16 Smart Fit
              </span>
            </div>
            <p className="text-small text-muted">{t.hub.postvDesc}</p>
          </div>
          <Link to="/postv" className="ui-btn ui-btn-ink ui-btn-sm self-start">
            {t.hub.postvCta}
          </Link>
        </Card>

        {/* 3. Chatting — Vàng · Đen */}
        <Card className="flex flex-col justify-between gap-4 border-[#FACC15]/40 bg-[#131720] p-5">
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="flex h-8 w-8 items-center justify-center rounded-inner bg-[#FACC15] text-[#0B0D12]">
                  <MessagesSquareIcon size={18} />
                </span>
                <h2 className="text-body font-extrabold">{t.hub.chattingTitle}</h2>
              </div>
              <span className="rounded-pill bg-[#FACC15]/20 px-2.5 py-0.5 text-tiny font-bold text-[#FACC15]">
                9:16 Smart Fit
              </span>
            </div>
            <p className="text-small text-muted">{t.hub.chattingDesc}</p>
          </div>
          <Link to="/chatting" className="ui-btn ui-btn-accent ui-btn-sm self-start">
            {t.hub.chattingCta}
          </Link>
        </Card>
      </section>

      {isPending && <HomeSkeleton />}
      {error && (
        <div className="space-y-3">
          <ErrorNote error={error} />
          <Button tone="soft" onClick={() => void refetch()}>
            {vi.common.retry}
          </Button>
        </div>
      )}
      {data && data.length === 0 && <EmptyProjects onCreate={openNew} />}
      {latest && (
        <>
          <div className="grid grid-cols-1 gap-6 min-[1024px]:grid-cols-[3fr_2fr]">
            <Continue project={latest} onDelete={(p) => setDeleting(p)} />
            {last ? (
              <LastExport project={last.project} render={last.render} />
            ) : (
              <section
                aria-label={t.lastExport}
                className="flex items-center justify-center rounded-card border border-[var(--card-border)] bg-hero p-6 text-on-hero"
              >
                <p className="text-body font-semibold">{t.last.none}</p>
              </section>
            )}
          </div>

          {recent.length > 0 && (
            <section aria-label={t.recent} className="space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-h2 font-bold">{t.recent}</h2>
                <Link to="/projects" className="ui-btn ui-btn-soft ui-btn-sm">
                  {t.seeAll}
                </Link>
              </div>
              <ul className="grid grid-cols-2 gap-6 min-[1024px]:grid-cols-4">
                {recent.map((p) => (
                  <RecentCard key={p.slug} project={p} onDelete={(p) => setDeleting(p)} />
                ))}
              </ul>
            </section>
          )}
        </>
      )}

      {/* KHO VIDEO ĐÃ XUẤT HỢP NHẤT (Tất cả · HBT Core · PostV · Chatting) */}
      <section aria-label="Video đã xuất gần đây" className="space-y-4 pt-2">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-h2 font-extrabold">Video đã xuất gần đây</h2>
            <p className="text-small text-muted">
              Tất cả thành phẩm `.mp4` từ HBT Core, PostV và Chatting tập trung tại một nơi duy
              nhất.
            </p>
          </div>
          <div
            role="tablist"
            aria-label="Lọc video theo động cơ"
            className="flex flex-wrap items-center gap-1.5 rounded-inner border border-line bg-card p-1"
          >
            {(['all', 'core', 'postv', 'chatting'] as const).map((eng) => {
              const active = engineFilter === eng;
              return (
                <button
                  key={eng}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  onClick={() => setEngineFilter(eng)}
                  className={`rounded-inner px-3 py-1.5 text-tiny font-bold transition-colors ${
                    active ? 'bg-[#D9232E] text-white' : 'text-muted hover:bg-soft hover:text-text'
                  }`}
                >
                  {ENGINE_LABELS[eng]}
                </button>
              );
            })}
          </div>
        </div>

        {filteredRenders.length === 0 ? (
          <Card className="flex flex-col items-center justify-center gap-2 py-8 text-center">
            <p className="text-body font-bold">Chưa có video đã xuất trong mục này</p>
            <p className="max-w-md text-small text-muted">
              Khi bạn xuất video từ HBT Core, PostV hoặc Chatting, thành phẩm 9:16 và nội dung đăng
              bài sẽ tự động hiện tại đây.
            </p>
          </Card>
        ) : (
          <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
            {filteredRenders.map((item) => (
              <Card
                key={item.id}
                as="li"
                padded={false}
                className="flex flex-col overflow-hidden border border-line bg-card"
              >
                <button
                  type="button"
                  onClick={() => setActiveRender(item)}
                  className="group relative aspect-[9/16] w-full overflow-hidden bg-[#0B0D12] text-left"
                  aria-label={`Xem thành phẩm: ${item.title}`}
                >
                  <video
                    src={item.video_url}
                    preload="metadata"
                    muted
                    playsInline
                    className="h-full w-full object-cover opacity-90 transition-opacity group-hover:opacity-100"
                  />
                  <span
                    className={`absolute top-2.5 left-2.5 rounded-pill border px-2.5 py-0.5 text-tiny font-extrabold uppercase ${ENGINE_BADGE_STYLE[item.engine]}`}
                  >
                    {ENGINE_LABELS[item.engine]}
                  </span>
                  {item.duration_sec > 0 && (
                    <span className="num absolute right-2.5 bottom-2.5 rounded bg-black/80 px-2 py-0.5 text-tiny font-bold text-white">
                      {formatDuration(item.duration_sec)}
                    </span>
                  )}
                </button>
                <div className="flex flex-1 flex-col justify-between gap-2 p-3.5">
                  <div>
                    <p className="line-clamp-2 text-small font-bold">{item.title}</p>
                    <p className="num mt-1 text-tiny text-muted">
                      {item.size_mb} MB · {item.created_at ? formatDate(item.created_at) : ''}
                    </p>
                  </div>
                  <div className="flex items-center justify-between gap-2 pt-1">
                    <Button
                      size="sm"
                      tone="brand"
                      onClick={() => setActiveRender(item)}
                      className="flex-1"
                    >
                      Xem & Đăng bài
                    </Button>
                    <Button
                      size="sm"
                      tone="ghost"
                      onClick={() => setDeletingRender(item)}
                      aria-label={`Xóa video ${item.title}`}
                    >
                      Xóa
                    </Button>
                  </div>
                </div>
              </Card>
            ))}
          </ul>
        )}
      </section>

      {/* Modal 9:16 Player + Publish.txt Copy + Download + Delete */}
      <Dialog
        open={Boolean(activeRender)}
        onClose={() => setActiveRender(null)}
        title={activeRender ? activeRender.title : 'Chi tiết video đã xuất'}
        className="!max-w-[760px]"
      >
        {activeRender && (
          <div className="grid grid-cols-1 gap-6 md:grid-cols-[240px_1fr]">
            <div className="mx-auto aspect-[9/16] w-full max-w-[240px] overflow-hidden rounded-inner border border-line bg-black">
              <video
                src={activeRender.video_url}
                controls
                autoPlay
                playsInline
                className="h-full w-full object-contain"
              />
            </div>
            <div className="flex flex-col justify-between gap-4">
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={`rounded-pill border px-2.5 py-0.5 text-tiny font-extrabold uppercase ${ENGINE_BADGE_STYLE[activeRender.engine]}`}
                  >
                    {ENGINE_LABELS[activeRender.engine]}
                  </span>
                  <span className="num text-small text-muted">
                    {activeRender.size_mb} MB
                    {activeRender.duration_sec > 0
                      ? ` · ${formatDuration(activeRender.duration_sec)}`
                      : ''}
                  </span>
                </div>

                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="text-small font-bold">Nội dung đăng bài (`publish.txt`)</span>
                    {activeRender.publish_text && (
                      <Button
                        size="sm"
                        tone="accent"
                        onClick={() => void handleCopyPublishText(activeRender.publish_text)}
                      >
                        Sao chép nội dung đăng bài
                      </Button>
                    )}
                  </div>
                  <pre className="max-h-52 overflow-y-auto rounded-inner border border-line bg-soft p-3 font-sans text-small whitespace-pre-wrap">
                    {activeRender.publish_text || 'Chưa có nội dung publish.txt đính kèm.'}
                  </pre>
                </div>
              </div>

              <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line pt-4">
                <div className="flex flex-wrap items-center gap-2">
                  <a
                    href={activeRender.video_url}
                    download={`${activeRender.slug || 'video'}.mp4`}
                    className="ui-btn ui-btn-brand ui-btn-sm"
                  >
                    Tải video.mp4
                  </a>
                  {activeRender.slug && (
                    <Link
                      to={
                        activeRender.engine === 'chatting'
                          ? `/chatting/${activeRender.slug}`
                          : activeRender.engine === 'postv'
                            ? `/postv/${activeRender.slug}`
                            : `/p/${activeRender.slug}`
                      }
                      className="ui-btn ui-btn-soft ui-btn-sm"
                      onClick={() => setActiveRender(null)}
                    >
                      Mở dự án gốc
                    </Link>
                  )}
                </div>
                <Button size="sm" tone="danger" onClick={() => setDeletingRender(activeRender)}>
                  Xóa video
                </Button>
              </div>
            </div>
          </div>
        )}
      </Dialog>

      {deleting && (
        <ConfirmDialog
          title={vi.projects.deleteTitle}
          message={vi.projects.confirmDelete(deleting.title)}
          confirmLabel={vi.projects.delete}
          danger
          busy={remove.isPending}
          onConfirm={() => remove.mutate(deleting.slug)}
          onCancel={() => setDeleting(null)}
        />
      )}

      {deletingRender && (
        <ConfirmDialog
          title="Xóa video đã xuất?"
          message={`Bạn có chắc muốn xóa vĩnh viễn video "${deletingRender.title}" khỏi ổ cứng?`}
          confirmLabel="Xóa vĩnh viễn"
          danger
          busy={deleteRenderMut.isPending}
          onConfirm={() => deleteRenderMut.mutate(deletingRender)}
          onCancel={() => setDeletingRender(null)}
        />
      )}
    </main>
  );
}
