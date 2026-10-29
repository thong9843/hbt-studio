import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, Navigate, Outlet, useNavigate, useParams } from 'react-router-dom';
import { api } from '../api/endpoints';
import { isPostv, type Project } from '../api/types';
import { PublishDrawer } from '../components/compose/PublishDrawer';
import { BackupsDialog } from '../components/script/BackupsDialog';
import { PasteJsonDialog } from '../components/script/PasteJsonDialog';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { ErrorNote } from '../components/ErrorNote';
import { ArrowLeftIcon, MoreIcon } from '../components/icons';
import { SaveIndicator } from '../components/SaveIndicator';
import { Button } from '../components/ui/Button';
import { Menu } from '../components/ui/Menu';
import { Input } from '../components/ui/Field';
import { ProjectEditorContext, type ProjectEditor } from '../hooks/projectEditor';
import { useRenderJob } from '../hooks/renderJob';
import { useToast } from '../hooks/toast';
import { useAutosave } from '../hooks/useAutosave';
import { vi } from '../i18n/vi';

function EditorProvider({ initial }: { initial: Project }) {
  const slug = initial.slug;
  const [project, setProject] = useState(initial);
  const latest = useRef(initial);
  const [savedCount, setSavedCount] = useState(0);
  const [imageVersion, setImageVersion] = useState(0);

  const save = useCallback(
    async (p: Project) => {
      await api.saveProject(slug, p);
      setSavedCount((n) => n + 1);
    },
    [slug],
  );
  const { status, error, schedule, flush, hasPending } = useAutosave(save);

  const commit = useCallback((next: Project) => {
    latest.current = next;
    setProject(next);
  }, []);

  const update = useCallback(
    (fn: (p: Project) => Project) => {
      const next = fn(latest.current);
      commit(next);
      schedule(next);
    },
    [commit, schedule],
  );

  const applyServer = useCallback(
    (fn: (p: Project) => Project) => {
      const next = fn(latest.current);
      commit(next);
      // Một lần lưu đang chờ mang bản cũ (chưa có kết quả máy chủ) sẽ ghi đè mất nó.
      if (hasPending()) schedule(next);
    },
    [commit, hasPending, schedule],
  );

  const bumpImages = useCallback(() => setImageVersion((n) => n + 1), []);

  const reorder = useCallback(
    async (order: number[]) => {
      await flush();
      const next = await api.reorderScenes(slug, order);
      commit(next);
      bumpImages();
    },
    [bumpImages, commit, flush, slug],
  );

  const deleteScene = useCallback(
    async (sceneIndex: number) => {
      await flush();
      const next = await api.deleteScene(slug, sceneIndex);
      commit(next);
      bumpImages();
    },
    [bumpImages, commit, flush, slug],
  );

  const uploadImage = useCallback(
    async (sceneIndex: number, file: File) => {
      await flush();
      const res = await api.uploadAsset(slug, 'image', file, sceneIndex);
      const image = res.project.scenes[sceneIndex]?.image ?? '';
      applyServer((p) => ({
        ...p,
        scenes: p.scenes.map((s, i) => (i === sceneIndex ? { ...s, image } : s)),
      }));
      bumpImages();
    },
    [applyServer, bumpImages, flush, slug],
  );

  const toast = useToast();
  useEffect(() => {
    if (status === 'error' && error) toast.error(new Error(error), () => void flush());
    // Chỉ báo mỗi lần chuyển sang trạng thái lỗi.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault();
        void flush();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [flush]);

  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => {
      if (status === 'dirty' || status === 'saving' || status === 'error') e.preventDefault();
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [status]);

  const editor: ProjectEditor = useMemo(
    () => ({
      project,
      update,
      applyServer,
      flush,
      status,
      saveError: error,
      savedCount,
      imageVersion,
      bumpImages,
      reorder,
      deleteScene,
      uploadImage,
    }),
    [
      project,
      update,
      applyServer,
      flush,
      status,
      error,
      savedCount,
      imageVersion,
      bumpImages,
      reorder,
      deleteScene,
      uploadImage,
    ],
  );

  const [publishOpen, setPublishOpen] = useState(false);
  const [pasteOpen, setPasteOpen] = useState(false);
  const [backupsOpen, setBackupsOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const job = useRenderJob();
  const rendering = job.running && job.slug === slug;
  const removeProject = useMutation({
    mutationFn: async () => {
      await flush(); // không để lần lưu tự động nào còn chờ sau khi dự án đã bị xoá
      await api.deleteProject(slug);
    },
    onSuccess: () => {
      toast.info(vi.projects.deleted);
      void queryClient.invalidateQueries({ queryKey: ['projects'] });
      queryClient.removeQueries({ queryKey: ['project', slug] });
      navigate('/projects');
    },
    onError: (e) => {
      setConfirmDelete(false);
      toast.error(e);
    },
  });
  return (
    <ProjectEditorContext.Provider value={editor}>
      <main className="mx-auto max-w-[1440px] px-6 py-5">
        <header className="flex min-h-12 flex-wrap items-center gap-3">
          <Link
            to="/projects"
            aria-label={vi.compose.back}
            title={vi.compose.back}
            className="ui-icon-btn ui-icon-btn-sm"
          >
            <ArrowLeftIcon size={20} />
          </Link>
          <div className="min-w-[12rem] flex-1">
            <Input
              aria-label={vi.compose.meta.title}
              className="!min-h-12 !bg-transparent !text-title !font-extrabold"
              value={project.title}
              onChange={(e) => update((p) => ({ ...p, title: e.target.value }))}
            />
          </div>
          <SaveIndicator status={status} error={error} />
          <Button tone="soft" size="sm" className="ml-auto" onClick={() => setPasteOpen(true)}>
            {vi.script.open}
          </Button>
          <Button tone="soft" size="sm" onClick={() => setPublishOpen(true)}>
            {vi.compose.publishPanel.open}
          </Button>
          <Menu
            label={vi.script.menu}
            icon={<MoreIcon size={20} />}
            items={[
              {
                key: 'backups',
                label: vi.script.backups.menu,
                onSelect: () => setBackupsOpen(true),
              },
              {
                key: 'delete',
                label: vi.compose.deleteProject,
                danger: true,
                disabled: rendering,
                reason: rendering ? vi.projects.renderingReason : undefined,
                onSelect: () => setConfirmDelete(true),
              },
            ]}
          />
        </header>
        <div className="mt-5">
          <Outlet />
        </div>
        <PublishDrawer open={publishOpen} onClose={() => setPublishOpen(false)} />
        <PasteJsonDialog open={pasteOpen} onClose={() => setPasteOpen(false)} />
        <BackupsDialog open={backupsOpen} onClose={() => setBackupsOpen(false)} />
        {confirmDelete && (
          <ConfirmDialog
            title={vi.projects.deleteTitle}
            message={vi.projects.confirmDelete(project.title)}
            confirmLabel={vi.projects.delete}
            danger
            busy={removeProject.isPending}
            onConfirm={() => removeProject.mutate()}
            onCancel={() => !removeProject.isPending && setConfirmDelete(false)}
          />
        )}
      </main>
    </ProjectEditorContext.Provider>
  );
}

export function ComposePage() {
  const { slug = '' } = useParams();
  const { data, isPending, error } = useQuery({
    queryKey: ['project', slug],
    queryFn: () => api.getAnyProject(slug),
    staleTime: Infinity,
    gcTime: 0,
    refetchOnWindowFocus: false,
    retry: false,
  });

  if (isPending)
    return (
      <main className="mx-auto flex max-w-[1440px] items-center gap-3 px-6 py-12 text-muted">
        <span className="ui-spinner" aria-hidden="true" />
        {vi.compose.loading}
      </main>
    );
  if (error || !data) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-10">
        <ErrorNote error={error} />
        <Link to="/projects" className="ui-btn ui-btn-soft mt-4">
          {vi.compose.back}
        </Link>
      </main>
    );
  }
  if (isPostv(data)) return <Navigate to={`/postv/${slug}`} replace />; // dự án PostV có màn riêng
  return <EditorProvider key={slug} initial={data} />;
}
