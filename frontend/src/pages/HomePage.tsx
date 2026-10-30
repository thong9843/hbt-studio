import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/endpoints';
import type { ProjectSummary, RenderSummary } from '../api/types';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { EmptyProjects } from '../components/EmptyProjects';
import { ErrorNote } from '../components/ErrorNote';
import { CheckIcon, MoreIcon, PlayIcon } from '../components/icons';
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
import { latestExport, readiness } from '../utils/readiness';

const RECENT = 4;
const TONE = { final: 'red', preview: 'yel', none: 'neutral', broken: 'danger' } as const;

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
    <Card as="li" padded={false} className="ui-card-link overflow-hidden">
      <Link to={href} aria-label={`${vi.projects.open}: ${project.title}`} className="block">
        <div className="aspect-[9/16] w-full overflow-hidden bg-soft">
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
  const queryClient = useQueryClient();
  const toast = useToast();

  const { data, isPending, error, refetch } = useQuery({
    queryKey: ['projects'],
    queryFn: api.listProjects,
  });

  const remove = useMutation({
    mutationFn: (slug: string) => api.deleteProject(slug),
    onSuccess: () => {
      setDeleting(null);
      void queryClient.invalidateQueries({ queryKey: ['projects'] });
      toast.info(vi.projects.deleted);
    },
    onError: (e) => {
      setDeleting(null);
      toast.error(e);
    },
  });

  // Danh sách đã sắp theo `updated_at` mới nhất trước.
  const latest = data?.[0];
  const last = data ? latestExport(data) : null;
  const recent = data?.slice(1, 1 + RECENT) ?? [];

  return (
    <main className="mx-auto max-w-[1280px] space-y-8 px-6 py-10">
      <h1 className="text-display font-extrabold uppercase">{t.title}</h1>

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
        </>
      )}
    </main>
  );
}
