import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/endpoints';
import type { ProjectSummary, UnifiedRenderItem } from '../api/types';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { EmptyProjects } from '../components/EmptyProjects';
import { ErrorNote } from '../components/ErrorNote';
import { EngineShowcaseCards } from '../components/home/EngineShowcaseCards';
import { RenderPlayerModal } from '../components/home/RenderPlayerModal';
import {
  CheckIcon,
  CopyIcon,
  DownloadIcon,
  MoreIcon,
  PlayIcon,
  SearchIcon,
  TrashIcon,
} from '../components/icons';
import { CardImage } from '../components/ProjectCard';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Menu } from '../components/ui/Menu';
import { Skeleton } from '../components/ui/Skeleton';
import { useNewProject } from '../hooks/newProject';
import { useToast } from '../hooks/toast';
import { vi } from '../i18n/vi';
import { formatDate, formatDuration } from '../utils/format';
import { projectHref } from '../utils/projectHref';
import { projectImage, projectStatus } from '../utils/projectStatus';
import { readiness } from '../utils/readiness';

const RECENT = 4;
const TONE = { final: 'red', preview: 'yel', none: 'neutral', broken: 'danger' } as const;

const ENGINE_LABELS: Record<'all' | 'core' | 'postv' | 'chatting' | 'stickv', string> = {
  all: 'Tất cả',
  core: 'HBT Core',
  postv: 'PostV',
  chatting: 'Chatting',
  stickv: 'StickV',
};

function getTimeGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'Chào buổi sáng';
  if (hour < 18) return 'Chào buổi chiều';
  return 'Chào buổi tối';
}

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

/** Thẻ "Tiếp tục dự án dở": dự án sửa gần nhất. */
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
    enabled: project.kind !== 'postv',
  });
  const ready = brief.data ? readiness(brief.data) : null;
  const series = brief.data?.series;
  const video = project.last_final?.video ?? project.last_render?.video ?? null;
  const fallbackKind = project.kind === 'postv' ? 'postv' : 'core';

  return (
    <Card as="section" aria-label={t.continue} className="flex flex-col gap-5 sm:flex-row">
      <div className="aspect-[9/16] w-[124px] shrink-0 overflow-hidden rounded-inner border border-line bg-soft">
        <CardImage src={projectImage(project)} fallbackKind={fallbackKind} />
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-2.5">
        <div className="flex items-center justify-between gap-2">
          <p className="text-tiny font-bold uppercase tracking-wider text-muted">{t.continue}</p>
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
        <h2 className="line-clamp-2 text-title font-extrabold text-text">{project.title}</h2>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={fallbackKind}>{fallbackKind === 'postv' ? vi.postv.badge : 'HBT'}</Badge>
          <Badge tone={TONE[status.kind]}>{status.label}</Badge>
          {series && <span className="text-small text-muted">{series}</span>}
        </div>
        {ready ? (
          <ul className="mt-1 flex flex-wrap gap-x-4 gap-y-1.5" aria-label={t.dot.label}>
            <Dot
              on={ready.images.total > 0 && ready.images.done === ready.images.total}
              label={t.dot.images(ready.images.done, ready.images.total)}
            />
            <Dot on={ready.voice} label={t.dot.voice} />
            <Dot on={ready.music} label={t.dot.music} />
            <Dot on={ready.cover} label={t.dot.cover} />
          </ul>
        ) : (
          project.kind !== 'postv' && !brief.isError && <Skeleton width={240} height={20} />
        )}
        <div className="mt-auto flex flex-wrap items-center gap-2 pt-2">
          <Link to={projectHref(project)} className="ui-btn ui-btn-ink ui-btn-sm">
            Mở lại dự án
          </Link>
          {video && (
            <a
              href={video}
              target="_blank"
              rel="noreferrer"
              className="ui-btn ui-btn-soft ui-btn-sm"
            >
              <PlayIcon size={14} />
              {t.watch}
            </a>
          )}
        </div>
      </div>
    </Card>
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
  const fallbackKind = project.kind === 'postv' ? 'postv' : 'core';
  return (
    <Card as="li" padded={false} className="ui-card-link flex flex-col overflow-hidden">
      <Link to={href} aria-label={`${vi.projects.open}: ${project.title}`} className="block">
        <div className="aspect-[9/16] w-full overflow-hidden bg-soft">
          <CardImage src={projectImage(project)} fallbackKind={fallbackKind} />
        </div>
      </Link>
      <div className="flex flex-1 items-start justify-between gap-2 p-3.5">
        <div className="min-w-0 flex-1 space-y-1.5">
          <p className="line-clamp-2 text-small font-bold text-text">
            <Link to={href} className="hover:underline">
              {project.title}
            </Link>
          </p>
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge tone={fallbackKind}>{fallbackKind === 'postv' ? vi.postv.badge : 'HBT'}</Badge>
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

function RenderCoverPreview({ item }: { item: UnifiedRenderItem }) {
  const [imgFailed, setImgFailed] = useState(false);

  if (item.cover_url && !imgFailed) {
    return (
      <img
        src={item.cover_url}
        alt={item.title}
        className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
        loading="lazy"
        onError={() => setImgFailed(true)}
      />
    );
  }

  return (
    <video
      src={`${item.video_url}#t=0.5`}
      muted
      playsInline
      preload="metadata"
      poster="/brand/hay-biet-tuot_avatar.png"
      className="h-full w-full object-cover"
    />
  );
}

export function HomePage() {
  const { open: openNew } = useNewProject();
  const [searchQuery, setSearchQuery] = useState('');
  const [deleting, setDeleting] = useState<ProjectSummary | null>(null);
  const [engineFilter, setEngineFilter] = useState<
    'all' | 'core' | 'postv' | 'chatting' | 'stickv'
  >('all');
  const [activeRender, setActiveRender] = useState<UnifiedRenderItem | null>(null);
  const [deletingRender, setDeletingRender] = useState<UnifiedRenderItem | null>(null);
  const queryClient = useQueryClient();
  const toast = useToast();

  const { data, isPending, error, refetch } = useQuery({
    queryKey: ['projects'],
    queryFn: api.listProjects,
  });

  const rendersQuery = useQuery({
    queryKey: ['unified-renders'],
    queryFn: () => api.listUnifiedRenders(),
    retry: false,
  });

  const musicHubQuery = useQuery({
    queryKey: ['asset-hub', 'music'],
    queryFn: () => api.listAssetHub('music'),
    retry: false,
  });

  const bgHubQuery = useQuery({
    queryKey: ['asset-hub', 'backgrounds'],
    queryFn: () => api.listAssetHub('backgrounds'),
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

  const q = searchQuery.trim().toLowerCase();

  const filteredProjects = useMemo(() => {
    const list = data ?? [];
    if (!q) return list;
    return list.filter(
      (p) => p.title.toLowerCase().includes(q) || p.slug.toLowerCase().includes(q),
    );
  }, [data, q]);

  const latest = filteredProjects[0];
  const recent = filteredProjects.slice(1, 1 + RECENT);

  const allRenders = useMemo(() => rendersQuery.data?.items ?? [], [rendersQuery.data?.items]);
  const filteredRenders = useMemo(() => {
    return allRenders.filter((r) => {
      if (engineFilter !== 'all' && r.engine !== engineFilter) return false;
      if (q && !r.title.toLowerCase().includes(q) && !r.slug.toLowerCase().includes(q))
        return false;
      return true;
    });
  }, [allRenders, engineFilter, q]);

  const totalAssets =
    (musicHubQuery.data?.items.length ?? 0) + (bgHubQuery.data?.items.length ?? 0);

  const handleCopyPublishText = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      toast.info('Đã sao chép nội dung đăng bài!');
    } catch (err) {
      toast.error(err);
    }
  };

  return (
    <main className="w-full max-w-full space-y-8 px-6 py-7 lg:px-8">
      {/* Header Chào mừng Sáng tạo — Thoáng đãng, không dùng hộp đen */}
      <header className="flex flex-col gap-5 rounded-card border border-line bg-card/80 p-6 shadow-card backdrop-blur-sm lg:flex-row lg:items-center lg:justify-between">
        <div className="space-y-2">
          <div className="inline-flex items-center gap-2 rounded-pill border border-line bg-soft px-3 py-1 text-tiny font-bold text-text-2">
            <img src="/brand/hay-biet-tuot_avatar.png" alt="" className="h-4 w-4 rounded-full" />
            <span>HBT Studio v5.0 · Next-Gen Creator Workstation</span>
          </div>
          <h1 className="text-h1 font-extrabold text-text">
            {getTimeGreeting()}, hôm nay làm video gì?
          </h1>
          <p className="text-small text-muted">
            Chọn nhanh động cơ bên dưới hoặc tiếp tục dự án đang biên tập của kênh Hay Biết Tuốt.
          </p>
        </div>

        {/* Thanh tìm kiếm & 3 Chỉ số tổng quan từ API/DB */}
        <div className="flex flex-col gap-3 sm:items-end">
          <div className="relative w-full sm:w-[320px]">
            <SearchIcon
              size={16}
              className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted"
            />
            <input
              type="search"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Tìm dự án hoặc video đã xuất..."
              aria-label="Tìm dự án hoặc video đã xuất"
              className="ui-input !min-h-[42px] !pl-10 text-small"
            />
          </div>

          <div className="grid grid-cols-3 gap-2.5">
            <div className="rounded-inner border border-line bg-soft/70 px-3.5 py-2 text-center">
              <div className="num text-title font-extrabold text-text">{allRenders.length}</div>
              <div className="text-[11px] font-semibold text-muted">Video đã xuất</div>
            </div>
            <div className="rounded-inner border border-line bg-soft/70 px-3.5 py-2 text-center">
              <div className="num text-title font-extrabold text-text">{data?.length ?? 0}</div>
              <div className="text-[11px] font-semibold text-muted">Dự án đang dở</div>
            </div>
            <div className="rounded-inner border border-line bg-soft/70 px-3.5 py-2 text-center">
              <div className="num text-title font-extrabold text-text">{totalAssets}</div>
              <div className="text-[11px] font-semibold text-muted">Tài nguyên sẵn có</div>
            </div>
          </div>
        </div>
      </header>

      {/* 3 Thẻ Động cơ Sáng tạo tương tác */}
      <EngineShowcaseCards />

      {error && (
        <div className="space-y-2">
          <ErrorNote error={error} />
          <Button size="sm" tone="soft" onClick={() => void refetch()}>
            {vi.common.retry}
          </Button>
        </div>
      )}

      {/* Khu vực Tiếp tục dự án dở */}
      <section aria-label="Tiếp tục dự án dở" className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-title font-extrabold text-text">Tiếp tục dự án dở</h2>
          <Link to="/projects" className="text-small font-bold text-engine-postv hover:underline">
            Xem tất cả dự án →
          </Link>
        </div>

        {isPending ? (
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            <Skeleton height={220} className="!rounded-card" />
            <Skeleton height={220} className="!rounded-card" />
          </div>
        ) : filteredProjects.length === 0 ? (
          <EmptyProjects onCreate={() => openNew()} />
        ) : (
          <div className="space-y-5">
            {latest && <Continue project={latest} onDelete={setDeleting} />}
            {recent.length > 0 && (
              <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
                {recent.map((p) => (
                  <RecentCard key={p.slug} project={p} onDelete={setDeleting} />
                ))}
              </ul>
            )}
          </div>
        )}
      </section>

      {/* Khu vực Video đã xuất gần đây (GET /api/renders) */}
      <section aria-label="Video đã xuất gần đây" className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-title font-extrabold text-text">Video đã xuất gần đây</h2>
            <p className="text-small text-muted">
              Đồng bộ trực tiếp từ thư viện thành phẩm 9:16 của HBT Core, PostV, Chatting và StickV.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            {(['all', 'core', 'postv', 'chatting', 'stickv'] as const).map((eng) => {
              const active = engineFilter === eng;
              return (
                <button
                  key={eng}
                  type="button"
                  onClick={() => setEngineFilter(eng)}
                  aria-pressed={active}
                  className={`ui-chip ui-chip-sm ${active ? '!bg-primary !text-on-primary' : ''}`}
                >
                  {ENGINE_LABELS[eng]}
                </button>
              );
            })}
          </div>
        </div>

        {rendersQuery.isPending ? (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} height={320} className="!rounded-card" />
            ))}
          </div>
        ) : filteredRenders.length === 0 ? (
          <Card className="py-10 text-center">
            <p className="text-body font-bold text-text">Chưa có video nào được xuất ở mục này</p>
            <p className="mt-1 text-small text-muted">
              Chọn một động cơ phía trên để tạo và xuất video 9:16 đầu tiên.
            </p>
          </Card>
        ) : (
          <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
            {filteredRenders.slice(0, 8).map((item) => (
              <Card
                key={item.id}
                as="li"
                padded={false}
                className="group flex flex-col overflow-hidden transition-all duration-180 hover:-translate-y-0.5 hover:shadow-card-hover"
              >
                <button
                  type="button"
                  onClick={() => setActiveRender(item)}
                  className="relative aspect-[9/16] w-full overflow-hidden bg-hero text-left"
                  aria-label={`Xem video ${item.title}`}
                >
                  <RenderCoverPreview item={item} />
                  <div className="absolute inset-0 bg-gradient-to-t from-black/75 via-transparent to-black/25 opacity-80 transition-opacity group-hover:opacity-100" />
                  <span className="absolute left-2.5 top-2.5">
                    <Badge tone={item.engine}>{ENGINE_LABELS[item.engine]}</Badge>
                  </span>
                  <span className="absolute inset-0 flex items-center justify-center opacity-0 transition-opacity group-hover:opacity-100">
                    <span className="flex h-12 w-12 items-center justify-center rounded-full bg-white/90 text-slate-900 shadow-lg">
                      <PlayIcon size={20} />
                    </span>
                  </span>
                  {item.duration_sec > 0 && (
                    <span className="num absolute bottom-2.5 right-2.5 rounded-md bg-black/75 px-2 py-0.5 text-tiny font-bold text-white backdrop-blur-sm">
                      {formatDuration(item.duration_sec)}
                    </span>
                  )}
                </button>

                <div className="flex flex-1 flex-col justify-between gap-2.5 p-3.5">
                  <div>
                    <p className="line-clamp-2 text-small font-bold text-text">{item.title}</p>
                    <p className="num mt-1 text-tiny text-muted">
                      {item.size_mb} MB
                      {item.created_at ? ` · ${formatDate(item.created_at)}` : ''}
                    </p>
                  </div>

                  <div className="flex flex-wrap items-center gap-1.5 pt-1">
                    <Button
                      size="sm"
                      tone="ink"
                      icon={<PlayIcon size={13} />}
                      onClick={() => setActiveRender(item)}
                      className="flex-1"
                    >
                      Xem video
                    </Button>
                    <a
                      href={item.video_url}
                      download={`${item.slug || 'video'}.mp4`}
                      title="Tải .mp4"
                      aria-label={`Tải ${item.title}`}
                      className="ui-icon-btn ui-icon-btn-sm bg-soft"
                    >
                      <DownloadIcon size={14} />
                    </a>
                    {item.publish_text && (
                      <button
                        type="button"
                        onClick={() => void handleCopyPublishText(item.publish_text)}
                        title="Copy caption (publish.txt)"
                        aria-label={`Copy caption ${item.title}`}
                        className="ui-icon-btn ui-icon-btn-sm bg-soft"
                      >
                        <CopyIcon size={14} />
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => setDeletingRender(item)}
                      title="Xóa video"
                      aria-label={`Xóa video ${item.title}`}
                      className="ui-icon-btn ui-icon-btn-sm text-danger hover:bg-danger-soft"
                    >
                      <TrashIcon size={14} />
                    </button>
                  </div>
                </div>
              </Card>
            ))}
          </ul>
        )}
      </section>

      <RenderPlayerModal
        item={activeRender}
        onClose={() => setActiveRender(null)}
        onCopyPublish={(text) => void handleCopyPublishText(text)}
        onRequestDelete={(item) => setDeletingRender(item)}
      />

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
