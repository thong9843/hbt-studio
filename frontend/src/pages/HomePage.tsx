import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { api, fileUrl, projectFileUrl } from '../api/endpoints';
import { fetchHealth } from '../api/health';
import type { Project, ProjectSummary, RenderSummary, UnifiedRenderItem } from '../api/types';
import { CardImage } from '../components/CardImage';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { EmptyState } from '../components/EmptyState';
import { ErrorBanner } from '../components/ErrorBanner';
import { useNewProject } from '../components/NewProjectDialog';
import { useToast } from '../components/Toast';
import { MoreIcon, PlayIcon } from '../components/icons';
import { Badge, Button, Card, Dialog, Menu, Skeleton } from '../components/ui';
import { formatDate, formatDuration } from '../i18n/format';
import { vi } from '../i18n/vi';
import {
  lastRender,
  projectHref,
  projectImage,
  projectReady,
  projectStatus,
  sortByRecent,
  type StatusKind,
} from '../lib/project';

const TONE: Record<StatusKind, 'ok' | 'warn' | 'err' | 'muted'> = {
  done: 'ok',
  draft: 'warn',
  error: 'err',
  idle: 'muted',
};

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
  const state = on ? vi.home.continue.dot.done : vi.home.continue.dot.todo;
  return (
    <li className="inline-flex items-center gap-1.5 text-small text-muted">
      <span
        aria-hidden="true"
        className={`h-2 w-2 rounded-full ${on ? 'bg-ok' : 'border border-muted bg-transparent'}`}
      />
      <span>{label}</span>
      <span className="sr-only">({state})</span>
    </li>
  );
}

/**
 * Thẻ "Tiếp tục làm": chỉ gọi thêm chi tiết cho đúng 1 dự án đầu danh sách
 * để biết trạng thái Ảnh/Giọng/Nhạc/Bìa và tên series.
 */
function ContinueCard({
  project,
  onDelete,
}: {
  project: ProjectSummary;
  onDelete: (p: ProjectSummary) => void;
}) {
  const t = vi.home.continue;
  const status = projectStatus(project);
  const brief = useQuery({
    queryKey: ['project', project.slug],
    queryFn: () => api.getProject(project.slug),
    enabled: project.kind !== 'postv',
    staleTime: 30_000,
    retry: false,
  });
  const detail = brief.data && brief.data.kind !== 'postv' ? (brief.data as Project) : undefined;
  const ready = detail ? projectReady(detail) : null;
  const series = detail?.series?.trim();
  const last = lastRender(project);
  const video = last?.video
    ? last.video.startsWith('/api/')
      ? last.video
      : fileUrl(last.video)
    : last?.job_id && project.kind !== 'postv'
      ? projectFileUrl(project.slug, `renders/${last.job_id}/video.mp4`)
      : null;

  return (
    <Card
      as="section"
      aria-label={t.title}
      className="flex flex-col gap-5 sm:flex-row sm:items-stretch"
    >
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
    queryFn: () => api.listProjects(),
  });

  const rendersQuery = useQuery({
    queryKey: ['unified-renders'],
    queryFn: () => api.listUnifiedRenders(),
    retry: false,
  });

  const deleteMut = useMutation({
    mutationFn: (p: ProjectSummary) =>
      p.kind === 'postv' ? api.deletePostvProject(p.slug) : api.deleteProject(p.slug),
    onSuccess: (_res, p) => {
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      toast.show(vi.projects.deleted(p.title), 'ok');
      setDeleting(null);
    },
    onError: (err) => {
      toast.show(err instanceof Error ? err.message : vi.projects.deleteFail, 'err');
      setDeleting(null);
    },
  });

  const deleteRenderMut = useMutation({
    mutationFn: (item: UnifiedRenderItem) => api.deleteUnifiedRender(item.id),
    onSuccess: (_res, item) => {
      queryClient.invalidateQueries({ queryKey: ['unified-renders'] });
      toast.show(`Đã xóa video "${item.title}"`, 'ok');
      if (activeRender?.id === item.id) setActiveRender(null);
      setDeletingRender(null);
    },
    onError: (err) => {
      toast.show(err instanceof Error ? err.message : 'Không xóa được video.', 'err');
      setDeletingRender(null);
    },
  });

  const sorted = data ? sortByRecent(data) : [];
  const current = sorted[0];
  const recent = sorted.slice(1, 5);
  const latestExport = sorted
    .map((project) => ({ project, render: lastRender(project) }))
    .filter((x): x is { project: ProjectSummary; render: RenderSummary } => Boolean(x.render))
    .sort((a, b) => b.render.created_at.localeCompare(a.render.created_at))[0];

  const allRenders = rendersQuery.data ?? [];
  const filteredRenders =
    engineFilter === 'all' ? allRenders : allRenders.filter((r) => r.engine === engineFilter);

  const handleCopyPublishText = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      toast.show('Đã sao chép nội dung đăng bài!', 'ok');
    } catch {
      toast.show('Không thể sao chép tự động.', 'err');
    }
  };

  return (
    <div className="space-y-8">
      {/* HBT Signature Hero Banner */}
      <header className="relative overflow-hidden rounded-card border border-white/10 bg-gradient-to-br from-[#131720] via-[#0B0D12] to-[#1A0B10] p-6 shadow-hover">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="mb-2 inline-flex items-center gap-2 rounded-pill border border-[#D9232E]/40 bg-[#D9232E]/15 px-3 py-1 text-tiny font-bold tracking-wider text-[#FACC15] uppercase">
              <span>HBT Signature Studio v4.0</span>
              <span className="text-white/40">•</span>
              <span className="text-white">Chuẩn 9:16 TikTok / Reels / Shorts</span>
            </div>
            <h1 className="text-h1 font-extrabold tracking-tight text-white">{t.title}</h1>
            <p className="mt-1 text-body text-[#94A3B8]">
              Chọn ngay 1 trong 3 động cơ sản xuất video 9:16 hoặc quản lý kho thành phẩm bên dưới.
            </p>
          </div>
          <div
            aria-label="Trạng thái môi trường"
            className="flex flex-wrap items-center gap-2 text-tiny font-semibold"
          >
            <span className="inline-flex items-center gap-1.5 rounded-pill border border-white/10 bg-[#131720] px-3 py-1.5 text-white">
              <span
                className={`h-2 w-2 rounded-full ${health?.vieneu ? 'bg-ok' : 'bg-warn'}`}
                aria-hidden="true"
              />
              VieNeu-TTS
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-pill border border-white/10 bg-[#131720] px-3 py-1.5 text-white">
              <span
                className={`h-2 w-2 rounded-full ${coreAssets?.gemini_configured ? 'bg-ok' : 'bg-warn'}`}
                aria-hidden="true"
              />
              Gemini
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-pill border border-white/10 bg-[#131720] px-3 py-1.5 text-white">
              <span
                className={`h-2 w-2 rounded-full ${health?.ffmpeg ? 'bg-ok' : 'bg-err'}`}
                aria-hidden="true"
              />
              FFmpeg
            </span>
          </div>
        </div>
      </header>

      {/* 3 Bento Engine Cards (HBT Signature: Red-Black, White-Red-Black, Gold-Black) */}
      <section
        aria-label="Khởi tạo nhanh 3 Động cơ Studio"
        className="grid grid-cols-1 gap-5 md:grid-cols-3"
      >
        {/* 1. HBT Core — Đỏ · Đen */}
        <Link
          to="/projects"
          className="group relative flex flex-col justify-between overflow-hidden rounded-card border border-[#D9232E]/40 bg-gradient-to-b from-[#1E1116] to-[#131720] p-6 transition-all duration-150 hover:-translate-y-0.5 hover:border-[#D9232E] hover:shadow-[0_12px_30px_rgba(217,35,46,0.22)]"
        >
          <div>
            <div className="flex items-center justify-between gap-2">
              <span className="inline-flex items-center rounded-pill bg-[#D9232E] px-2.5 py-0.5 text-tiny font-extrabold tracking-wider text-white uppercase">
                HBT Core
              </span>
              <span className="text-tiny font-semibold text-[#FACC15]">9:16 Full-bleed Fill</span>
            </div>
            <h2 className="mt-3 text-title font-extrabold text-white group-hover:text-[#FACC15]">
              Video Kiến thức & Giải thích
            </h2>
            <p className="mt-1.5 text-small text-[#94A3B8]">
              Soạn kịch bản Gemini, VieNeu-TTS giọng chuẩn, phụ đề Karaoke ASS & đóng dấu bản quyền.
            </p>
          </div>
          <div className="mt-5 inline-flex items-center gap-1.5 text-small font-bold text-[#FACC15]">
            <span>Mở HBT Core Studio</span>
            <span aria-hidden="true" className="transition-transform group-hover:translate-x-1">
              →
            </span>
          </div>
        </Link>

        {/* 2. PostV — Trắng · Đỏ · Đen */}
        <Link
          to="/postv"
          className="group relative flex flex-col justify-between overflow-hidden rounded-card border border-white/25 bg-gradient-to-b from-[#1B2230] to-[#131720] p-6 transition-all duration-150 hover:-translate-y-0.5 hover:border-white hover:shadow-[0_12px_30px_rgba(255,255,255,0.14)]"
        >
          <div>
            <div className="flex items-center justify-between gap-2">
              <span className="inline-flex items-center rounded-pill bg-white px-2.5 py-0.5 text-tiny font-extrabold tracking-wider text-[#0B0D12] uppercase">
                PostV
              </span>
              <span className="text-tiny font-semibold text-white/80">9:16 Smart Fit Blur</span>
            </div>
            <h2 className="mt-3 text-title font-extrabold text-white group-hover:text-[#FACC15]">
              PostV Kể chuyện Reddit
            </h2>
            <p className="mt-1.5 text-small text-[#94A3B8]">
              Ghép nền Gameplay + khung bài đăng + giọng đọc tự động & phụ đề nổi bật.
            </p>
          </div>
          <div className="mt-5 inline-flex items-center gap-1.5 text-small font-bold text-white group-hover:text-[#FACC15]">
            <span>Tạo PostV ngay</span>
            <span aria-hidden="true" className="transition-transform group-hover:translate-x-1">
              →
            </span>
          </div>
        </Link>

        {/* 3. Chatting — Vàng · Đen */}
        <Link
          to="/chatting"
          className="group relative flex flex-col justify-between overflow-hidden rounded-card border border-[#FACC15]/40 bg-gradient-to-b from-[#231F12] to-[#131720] p-6 transition-all duration-150 hover:-translate-y-0.5 hover:border-[#FACC15] hover:shadow-[0_12px_30px_rgba(250,204,21,0.2)]"
        >
          <div>
            <div className="flex items-center justify-between gap-2">
              <span className="inline-flex items-center rounded-pill bg-[#FACC15] px-2.5 py-0.5 text-tiny font-extrabold tracking-wider text-[#0B0D12] uppercase">
                Chatting
              </span>
              <span className="text-tiny font-semibold text-[#FACC15]">9:16 Smart Fit + Media</span>
            </div>
            <h2 className="mt-3 text-title font-extrabold text-white group-hover:text-[#FACC15]">
              Chatting Tin nhắn Đời thường
            </h2>
            <p className="mt-1.5 text-small text-[#94A3B8]">
              Dựng hội thoại kịch tính bằng Gemini AI, chèn ảnh/video trong bong bóng chat & lồng tiếng.
            </p>
          </div>
          <div className="mt-5 inline-flex items-center gap-1.5 text-small font-bold text-[#FACC15]">
            <span>Mở Chatting Studio</span>
            <span aria-hidden="true" className="transition-transform group-hover:translate-x-1">
              →
            </span>
          </div>
        </Link>
      </section>

      {error && (
        <ErrorBanner message={error instanceof Error ? error.message : ''} onRetry={refetch} />
      )}

      {isPending && <HomeSkeleton />}

      {!isPending && !error && sorted.length === 0 && (
        <EmptyState
          title={t.empty.title}
          hint={t.empty.hint}
          action={
            <Button variant="primary" onClick={() => openNew()}>
              {t.empty.cta}
            </Button>
          }
        />
      )}

      {!isPending && !error && current && (
        <>
          <div className="grid grid-cols-1 gap-6 min-[1024px]:grid-cols-[3fr_2fr]">
            <ContinueCard project={current} onDelete={setDeleting} />
            {latestExport ? (
              <LastExport project={latestExport.project} render={latestExport.render} />
            ) : (
              <section
                aria-label={t.last.title}
                className="flex flex-col justify-center gap-1 rounded-card border border-[var(--card-border)] bg-hero p-6 text-on-hero"
              >
                <p className="text-tiny font-semibold opacity-80">{t.lastExport}</p>
                <p className="text-title font-bold">{t.last.empty}</p>
                <p className="text-small opacity-80">{t.last.emptyHint}</p>
              </section>
            )}
          </div>

          {recent.length > 0 && (
            <section aria-label={t.recent} className="space-y-4">
              <div className="flex items-baseline justify-between">
                <h2 className="text-h2 font-bold">{t.recent}</h2>
                <Link to="/projects" className="text-small font-semibold text-[#FACC15] hover:underline">
                  {t.seeAll}
                </Link>
              </div>
              <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 min-[1024px]:grid-cols-4">
                {recent.map((p) => (
                  <RecentCard key={p.slug} project={p} onDelete={setDeleting} />
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
            <h2 className="text-h2 font-extrabold text-white">Video đã xuất gần đây</h2>
            <p className="text-small text-[#94A3B8]">
              Tất cả thành phẩm `.mp4` từ HBT Core, PostV và Chatting tập trung tại một nơi duy nhất.
            </p>
          </div>
          <div
            role="tablist"
            aria-label="Lọc video theo động cơ"
            className="flex flex-wrap items-center gap-1.5 rounded-inner border border-white/10 bg-[#131720] p-1"
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
                    active
                      ? 'bg-[#D9232E] text-white shadow-sm'
                      : 'text-[#94A3B8] hover:bg-white/5 hover:text-white'
                  }`}
                >
                  {ENGINE_LABELS[eng]}
                </button>
              );
            })}
          </div>
        </div>

        {filteredRenders.length === 0 ? (
          <Card className="flex flex-col items-center justify-center gap-2 py-10 text-center">
            <p className="text-body font-bold text-white">Chưa có video đã xuất trong mục này</p>
            <p className="max-w-md text-small text-[#94A3B8]">
              Khi bạn xuất video từ HBT Core, PostV hoặc Chatting, thành phẩm 9:16 và nội dung đăng bài sẽ tự động hiện tại đây.
            </p>
          </Card>
        ) : (
          <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
            {filteredRenders.map((item) => (
              <Card
                key={item.id}
                as="li"
                padded={false}
                className="flex flex-col overflow-hidden border border-white/10 bg-[#131720] transition-transform duration-150 hover:-translate-y-0.5 hover:border-[#FACC15]/50"
              >
                <button
                  type="button"
                  onClick={() => setActiveRender(item)}
                  className="group relative aspect-[9/16] w-full overflow-hidden bg-[#0B0D12] text-left"
                  aria-label={`Xem thành phẩm: ${item.title}`}
                >
                  <video
                    src={item.url}
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
                  {item.duration > 0 && (
                    <span className="num absolute right-2.5 bottom-2.5 rounded bg-black/80 px-2 py-0.5 text-tiny font-bold text-white">
                      {formatDuration(item.duration)}
                    </span>
                  )}
                </button>
                <div className="flex flex-1 flex-col justify-between gap-2 p-3.5">
                  <div>
                    <p className="line-clamp-2 text-small font-bold text-white">{item.title}</p>
                    <p className="num mt-1 text-tiny text-[#94A3B8]">
                      {item.size_mb} MB · {formatDate(new Date(item.created_at * 1000).toISOString())}
                    </p>
                  </div>
                  <div className="flex items-center justify-between gap-2 pt-1">
                    <Button
                      size="sm"
                      variant="primary"
                      onClick={() => setActiveRender(item)}
                      className="flex-1"
                    >
                      Xem & Đăng bài
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
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
        wide
      >
        {activeRender && (
          <div className="grid grid-cols-1 gap-6 md:grid-cols-[260px_1fr]">
            <div className="mx-auto aspect-[9/16] w-full max-w-[260px] overflow-hidden rounded-inner border border-white/15 bg-black">
              <video
                src={activeRender.url}
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
                  <span className="num text-small text-[#94A3B8]">
                    {activeRender.size_mb} MB
                    {activeRender.duration > 0 ? ` · ${formatDuration(activeRender.duration)}` : ''}
                  </span>
                </div>

                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-small font-bold text-white">
                      Nội dung đăng bài (`publish.txt`)
                    </label>
                    {activeRender.publish_text && (
                      <Button
                        size="sm"
                        variant="accent"
                        onClick={() => handleCopyPublishText(activeRender.publish_text)}
                      >
                        Sao chép nội dung đăng bài
                      </Button>
                    )}
                  </div>
                  <pre className="max-h-56 overflow-y-auto rounded-inner border border-white/10 bg-[#0B0D12] p-3 font-sans text-small whitespace-pre-wrap text-[#F8FAFC]">
                    {activeRender.publish_text || 'Chưa có nội dung publish.txt đính kèm.'}
                  </pre>
                </div>
              </div>

              <div className="flex flex-wrap items-center justify-between gap-2 border-t border-white/10 pt-4">
                <div className="flex flex-wrap items-center gap-2">
                  <a
                    href={activeRender.url}
                    download={activeRender.filename || 'video.mp4'}
                    className="ui-btn ui-btn-primary"
                  >
                    Tải video.mp4
                  </a>
                  {activeRender.project_slug && (
                    <Link
                      to={
                        activeRender.engine === 'chatting'
                          ? `/chatting/${activeRender.project_slug}`
                          : activeRender.engine === 'postv'
                            ? `/postv/${activeRender.project_slug}`
                            : `/p/${activeRender.project_slug}`
                      }
                      className="ui-btn ui-btn-soft"
                      onClick={() => setActiveRender(null)}
                    >
                      Mở dự án gốc
                    </Link>
                  )}
                </div>
                <Button
                  variant="danger"
                  onClick={() => setDeletingRender(activeRender)}
                >
                  Xóa video
                </Button>
              </div>
            </div>
          </div>
        )}
      </Dialog>

      <ConfirmDialog
        open={Boolean(deleting)}
        title={vi.projects.deleteConfirmTitle}
        message={deleting ? vi.projects.deleteConfirm(deleting.title) : ''}
        confirmLabel={vi.projects.delete}
        danger
        busy={deleteMut.isPending}
        onConfirm={() => deleting && deleteMut.mutate(deleting)}
        onCancel={() => setDeleting(null)}
      />

      <ConfirmDialog
        open={Boolean(deletingRender)}
        title="Xóa video đã xuất?"
        message={
          deletingRender
            ? `Bạn có chắc muốn xóa vĩnh viễn video "${deletingRender.title}" khỏi ổ cứng?`
            : ''
        }
        confirmLabel="Xóa vĩnh viễn"
        danger
        busy={deleteRenderMut.isPending}
        onConfirm={() => deletingRender && deleteRenderMut.mutate(deletingRender)}
        onCancel={() => setDeletingRender(null)}
      />
    </div>
  );
}
