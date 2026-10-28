import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api/endpoints';
import type { ProjectSummary } from '../api/types';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { ErrorNote } from '../components/ErrorNote';
import { HealthStatus } from '../components/HealthStatus';
import { PlusIcon } from '../components/icons';
import { useNewProject } from '../hooks/newProject';
import { useToast } from '../hooks/toast';
import { vi } from '../i18n/vi';
import { formatDateTime, formatDuration } from '../utils/format';

/** Thẻ dự án: ảnh cảnh 1 tràn sát mép (9:16), tiêu đề chữ hoa, ngày và huy hiệu ngay dưới ảnh. */
export function ProjectCard({
  project,
  onDuplicate,
  onDelete,
  busy,
}: {
  project: ProjectSummary;
  onDuplicate: () => void;
  onDelete: () => void;
  busy?: boolean;
}) {
  const render = project.last_render;
  return (
    <li className="flex flex-col overflow-hidden rounded-card border border-border bg-surface">
      <Link
        to={`/p/${project.slug}`}
        aria-label={`${vi.projects.open}: ${project.title}`}
        className="block aspect-[9/16] w-full overflow-hidden bg-surface"
      >
        <img
          src={project.thumb ?? '/brand/hay-biet-tuot_avatar.png'}
          alt=""
          className="h-full w-full object-cover"
          loading="lazy"
        />
      </Link>
      <div className="flex flex-1 flex-col gap-2 p-4">
        <h3 className="text-small font-bold uppercase leading-5">
          <Link to={`/p/${project.slug}`} className="hover:underline">
            {project.title}
          </Link>
        </h3>
        <p className="text-small text-text-muted">
          {vi.projects.updatedAt}: <span className="num">{formatDateTime(project.updated_at)}</span>
        </p>
        <div className="mt-2">
          {project.error ? (
            <p className="chip chip-danger">{vi.projects.broken}</p>
          ) : render ? (
            <p className="chip chip-ok">
              {vi.projects.lastRender}
              {render.preview ? ` · ${vi.projects.previewRender}` : ''}
              {render.duration ? ` · ${formatDuration(render.duration)}` : ''}
            </p>
          ) : (
            <p className="chip chip-muted">{vi.projects.notRendered}</p>
          )}
        </div>
        <div className="mt-auto flex flex-wrap gap-2 pt-3">
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            disabled={busy}
            onClick={onDuplicate}
          >
            {vi.projects.duplicate}
          </button>
          <button
            type="button"
            className="btn btn-danger btn-sm"
            disabled={busy}
            onClick={onDelete}
          >
            {vi.projects.delete}
          </button>
        </div>
      </div>
    </li>
  );
}

export function ProjectsPage() {
  const [deleting, setDeleting] = useState<ProjectSummary | null>(null);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast();
  const { open: openNew } = useNewProject();
  const { data, isPending, error, refetch } = useQuery({
    queryKey: ['projects'],
    queryFn: api.listProjects,
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['projects'] });

  const duplicate = useMutation({
    mutationFn: (slug: string) => api.duplicateProject(slug),
    onSuccess: (copy) => {
      void refresh();
      navigate(`/p/${copy.slug}`);
    },
    onError: (e, slug) => toast.error(e, () => duplicate.mutate(slug)),
  });
  const remove = useMutation({
    mutationFn: (slug: string) => api.deleteProject(slug),
    onSuccess: () => {
      setDeleting(null);
      void refresh();
      toast.info(vi.projects.deleted);
    },
    onError: (e) => {
      setDeleting(null);
      toast.error(e);
    },
  });

  return (
    <main className="mx-auto max-w-[1280px] px-6 py-12">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <h1>{vi.projects.title}</h1>
        {/* Một nút chính mỗi màn: khi danh sách trống, nút nằm trong khối trống bên dưới. */}
        {data?.length !== 0 && (
          <button type="button" className="btn btn-primary" onClick={openNew}>
            <PlusIcon size={20} />
            {vi.projects.create}
          </button>
        )}
      </div>

      <div className="mt-12">
        <HealthStatus />
      </div>

      <section className="mt-12" aria-label={vi.projects.title}>
        {isPending && (
          <p className="flex items-center gap-3 text-text-muted">
            <span className="spinner" aria-hidden="true" />
            {vi.common.loading}
          </p>
        )}
        {error && (
          <div className="space-y-3">
            <ErrorNote error={error} />
            <button type="button" className="btn btn-secondary" onClick={() => void refetch()}>
              {vi.common.retry}
            </button>
          </div>
        )}
        {data && data.length === 0 && (
          <div className="flex flex-col items-center gap-6 rounded-card bg-surface p-12 text-center">
            <img src="/brand/hbt-logo-mark.png" alt="" className="h-20 w-auto" />
            <p className="text-hero font-extrabold uppercase">{vi.projects.emptyHero}</p>
            <p className="text-text-muted">{vi.projects.empty}</p>
            <button type="button" className="btn btn-primary" onClick={openNew}>
              {vi.projects.create}
            </button>
          </div>
        )}
        {data && data.length > 0 && (
          <ul className="grid grid-cols-1 gap-6 min-[640px]:grid-cols-2 min-[1024px]:grid-cols-3 min-[1280px]:grid-cols-4">
            {data.map((p) => (
              <ProjectCard
                key={p.slug}
                project={p}
                busy={duplicate.isPending || remove.isPending}
                onDuplicate={() => duplicate.mutate(p.slug)}
                onDelete={() => setDeleting(p)}
              />
            ))}
          </ul>
        )}
      </section>

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
    </main>
  );
}
