import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/endpoints';
import { isPostv, type ProjectKind, type ProjectSummary } from '../api/types';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { EmptyProjects } from '../components/EmptyProjects';
import { ErrorNote } from '../components/ErrorNote';
import { PlusIcon } from '../components/icons';
import { BackgroundLibraryCard } from '../components/postv/BackgroundLibrary';
import { ProjectCard, ProjectCardSkeleton } from '../components/ProjectCard';
import { Button } from '../components/ui/Button';
import { useNewProject } from '../hooks/newProject';
import { useRenderJob } from '../hooks/renderJob';
import { useToast } from '../hooks/toast';
import { vi } from '../i18n/vi';
import { projectHref } from '../utils/projectHref';

const SKELETONS = [0, 1, 2, 3];

/** Lưới dự án. `kind="postv"`: trang PostV riêng (chỉ dự án PostV, nút Tạo PostV). */
export function ProjectsPage({ kind }: { kind?: ProjectKind } = {}) {
  const [deleting, setDeleting] = useState<ProjectSummary | null>(null);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast();
  const render = useRenderJob();
  const { open: openNew } = useNewProject();
  const all = useQuery({
    queryKey: ['projects'],
    queryFn: api.listProjects,
  });
  const { isPending, error, refetch } = all;
  const data = kind ? all.data?.filter((p) => p.kind === kind) : all.data;
  const postvPage = kind === 'postv';
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['projects'] });

  // Dự án đang dựng thì menu bị khoá theo job toàn cục; 409 từ backend (vd job mở từ trước khi tải
  // lại trang) và mọi lỗi khác vẫn hiện Toast lỗi làm lưới an toàn.
  const duplicate = useMutation({
    mutationFn: (slug: string) => api.duplicateProject(slug),
    onSuccess: (copy) => {
      void refresh();
      navigate(projectHref({ slug: copy.slug, kind: isPostv(copy) ? 'postv' : 'video' }));
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
    <main className="mx-auto max-w-[1280px] px-6 py-10">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-h1 font-extrabold uppercase">
            {postvPage ? vi.postv.listTitle : vi.projects.title}
          </h1>
          {postvPage && (
            <p className="mt-1 text-small text-muted">
              {vi.postv.listLead}
              {data && data.length > 0 ? ` · ${vi.postv.listCount(data.length)}` : ''}
            </p>
          )}
        </div>
        {/* Một nút chính mỗi màn: khi danh sách trống, nút nằm trong khối trống bên dưới. */}
        {data && data.length > 0 && (
          <Button tone="brand" icon={<PlusIcon />} onClick={() => openNew(kind)}>
            {postvPage ? vi.postv.create : vi.projects.create}
          </Button>
        )}
      </div>

      <section className="mt-8" aria-label={vi.projects.title}>
        {isPending && (
          <ul
            className="grid grid-cols-2 gap-6 min-[1024px]:grid-cols-3 min-[1280px]:grid-cols-4"
            aria-busy="true"
          >
            {SKELETONS.map((i) => (
              <ProjectCardSkeleton key={i} />
            ))}
          </ul>
        )}
        {error && (
          <div className="space-y-3">
            <ErrorNote error={error} />
            <Button tone="soft" onClick={() => void refetch()}>
              {vi.common.retry}
            </Button>
          </div>
        )}
        {data && data.length === 0 && !postvPage && <EmptyProjects onCreate={() => openNew()} />}
        {data && data.length === 0 && postvPage && (
          <div className="flex flex-col items-center gap-4 rounded-card bg-card px-6 py-16 text-center">
            <h2 className="text-h1 font-extrabold uppercase">{vi.postv.emptyTitle}</h2>
            <p className="text-body text-muted">{vi.postv.emptyLead}</p>
            <Button tone="brand" size="lg" icon={<PlusIcon />} onClick={() => openNew('postv')}>
              {vi.postv.create}
            </Button>
          </div>
        )}
        {data && data.length > 0 && (
          <ul className="grid grid-cols-2 gap-6 min-[1024px]:grid-cols-3 min-[1280px]:grid-cols-4">
            {data.map((p) => (
              <ProjectCard
                key={p.slug}
                project={p}
                busy={duplicate.isPending || remove.isPending}
                rendering={render.running && render.slug === p.slug}
                onDuplicate={() => duplicate.mutate(p.slug)}
                onDelete={() => setDeleting(p)}
              />
            ))}
          </ul>
        )}
      </section>

      {postvPage && <BackgroundLibraryCard />}

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
