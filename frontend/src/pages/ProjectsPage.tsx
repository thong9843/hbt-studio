import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api/endpoints';
import type { ProjectSummary } from '../api/types';
import { ErrorNote } from '../components/ErrorNote';
import { HealthStatus } from '../components/HealthStatus';
import { vi } from '../i18n/vi';
import { formatDateTime, formatDuration } from '../utils/format';

function NewProjectDialog({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [title, setTitle] = useState('');
  const [series, setSeries] = useState('');
  const [sceneCount, setSceneCount] = useState(8);
  const create = useMutation({
    mutationFn: () =>
      api.createProject({ title: title.trim(), series: series.trim(), scene_count: sceneCount }),
    onSuccess: (project) => {
      void queryClient.invalidateQueries({ queryKey: ['projects'] });
      navigate(`/p/${project.slug}`);
    },
  });
  const t = vi.projects.dialog;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (title.trim()) create.mutate();
  };

  return (
    <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/50 p-4">
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby="new-project-title"
        onSubmit={submit}
        className="w-full max-w-md space-y-4 rounded-3xl bg-bg p-8 shadow-xl"
      >
        <h2 id="new-project-title" className="text-2xl">
          {t.title}
        </h2>
        <div>
          <label className="label" htmlFor="np-title">
            {t.name}
          </label>
          <input
            id="np-title"
            className="input"
            autoFocus
            required
            placeholder={t.namePlaceholder}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </div>
        <div>
          <label className="label" htmlFor="np-series">
            {t.series}
          </label>
          <input
            id="np-series"
            className="input"
            value={series}
            onChange={(e) => setSeries(e.target.value)}
          />
        </div>
        <div>
          <label className="label" htmlFor="np-scenes">
            {t.scenes}
          </label>
          <input
            id="np-scenes"
            type="number"
            min={3}
            max={12}
            className="input"
            value={sceneCount}
            onChange={(e) => setSceneCount(Math.min(12, Math.max(3, Number(e.target.value) || 8)))}
          />
        </div>
        <ErrorNote error={create.error} />
        <div className="flex justify-end gap-2">
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            {vi.common.cancel}
          </button>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={create.isPending || !title.trim()}
          >
            {create.isPending ? t.creating : t.submit}
          </button>
        </div>
      </form>
    </div>
  );
}

function ProjectCard({ project }: { project: ProjectSummary }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['projects'] });
  const duplicate = useMutation({
    mutationFn: () => api.duplicateProject(project.slug),
    onSuccess: (copy) => {
      void refresh();
      navigate(`/p/${copy.slug}`);
    },
  });
  const remove = useMutation({
    mutationFn: () => api.deleteProject(project.slug),
    onSuccess: refresh,
  });
  const render = project.last_render;

  return (
    <li className="card flex flex-col overflow-hidden">
      <Link
        to={`/p/${project.slug}`}
        className="block aspect-[9/16] max-h-80 w-full overflow-hidden bg-hbt-red"
      >
        <img
          src={project.thumb ?? '/brand/hay-biet-tuot_avatar.png'}
          alt=""
          className="h-full w-full object-cover"
          loading="lazy"
        />
      </Link>
      <div className="flex flex-1 flex-col gap-2 p-4">
        <h3 className="text-lg font-extrabold leading-tight">
          <Link to={`/p/${project.slug}`} className="hover:underline">
            {project.title}
          </Link>
        </h3>
        <p className="text-xs text-muted">
          {vi.projects.updatedAt}: {formatDateTime(project.updated_at)}
        </p>
        {project.error ? (
          <p className="chip chip-danger w-fit">{vi.projects.broken}</p>
        ) : render ? (
          <p className="chip chip-ok w-fit">
            {vi.projects.lastRender}
            {render.preview ? ` · ${vi.projects.previewRender}` : ''}
            {render.duration ? ` · ${formatDuration(render.duration)}` : ''}
          </p>
        ) : (
          <p className="chip chip-muted w-fit">{vi.projects.notRendered}</p>
        )}
        <div className="mt-auto flex gap-2 pt-2">
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            disabled={duplicate.isPending}
            onClick={() => duplicate.mutate()}
          >
            {vi.projects.duplicate}
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            disabled={remove.isPending}
            onClick={() => {
              if (window.confirm(vi.projects.confirmDelete(project.title))) remove.mutate();
            }}
          >
            {vi.projects.delete}
          </button>
        </div>
        <ErrorNote error={duplicate.error ?? remove.error} />
      </div>
    </li>
  );
}

export function ProjectsPage() {
  const [creating, setCreating] = useState(false);
  const { data, isPending, error } = useQuery({
    queryKey: ['projects'],
    queryFn: api.listProjects,
  });

  return (
    <main className="mx-auto max-w-[1400px] px-6 py-10">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <h1 className="text-5xl leading-none">{vi.projects.title}</h1>
        <button type="button" className="btn btn-accent" onClick={() => setCreating(true)}>
          {vi.projects.create}
        </button>
      </div>

      <div className="mt-8">
        <HealthStatus />
      </div>

      <section className="mt-10">
        {isPending && <p className="text-muted">{vi.common.loading}</p>}
        <ErrorNote error={error} />
        {data && data.length === 0 && (
          <div className="card flex flex-col items-center gap-4 p-12 text-center">
            <img src="/brand/hbt-logo-mark.png" alt="" className="h-20 w-auto" />
            <p className="text-lg font-bold">{vi.projects.empty}</p>
          </div>
        )}
        {data && data.length > 0 && (
          <ul className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-5">
            {data.map((p) => (
              <ProjectCard key={p.slug} project={p} />
            ))}
          </ul>
        )}
      </section>

      {creating && <NewProjectDialog onClose={() => setCreating(false)} />}
    </main>
  );
}
