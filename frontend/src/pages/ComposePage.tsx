import { useQuery } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, NavLink, Outlet, useParams } from 'react-router-dom';
import { api } from '../api/endpoints';
import type { Project } from '../api/types';
import { ErrorNote } from '../components/ErrorNote';
import { SaveIndicator } from '../components/SaveIndicator';
import { ProjectEditorContext, type ProjectEditor } from '../hooks/projectEditor';
import { useAutosave } from '../hooks/useAutosave';
import { vi } from '../i18n/vi';

const tab = ({ isActive }: { isActive: boolean }) =>
  `border-b-2 px-1 pb-2 text-sm font-extrabold uppercase tracking-wide transition ${
    isActive ? 'border-fg text-fg' : 'border-transparent text-muted hover:text-fg'
  }`;

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
      uploadImage,
    ],
  );

  const base = `/p/${slug}`;
  return (
    <ProjectEditorContext.Provider value={editor}>
      <main className="mx-auto max-w-[1400px] px-6 py-6">
        <div className="flex flex-wrap items-center gap-4">
          <Link to="/" className="btn btn-ghost btn-sm">
            ← {vi.compose.back}
          </Link>
          <input
            aria-label={vi.compose.meta.title}
            className="min-w-[12rem] flex-1 border-0 bg-transparent px-0 text-3xl font-extrabold uppercase tracking-tight focus:outline-none focus-visible:ring-0"
            value={project.title}
            onChange={(e) => update((p) => ({ ...p, title: e.target.value }))}
          />
          <SaveIndicator status={status} error={error} />
        </div>
        <nav aria-label={vi.compose.tabs.label} className="mt-4 flex gap-6 border-b border-border">
          <NavLink to={base} end className={tab}>
            {vi.compose.tabs.scenes}
          </NavLink>
          <NavLink to={`${base}/audio`} className={tab}>
            {vi.compose.tabs.audio}
          </NavLink>
          <NavLink to={`${base}/export`} className={tab}>
            {vi.compose.tabs.export}
          </NavLink>
        </nav>
        <div className="mt-6">
          <Outlet />
        </div>
      </main>
    </ProjectEditorContext.Provider>
  );
}

export function ComposePage() {
  const { slug = '' } = useParams();
  const { data, isPending, error } = useQuery({
    queryKey: ['project', slug],
    queryFn: () => api.getProject(slug),
    staleTime: Infinity,
    gcTime: 0,
    refetchOnWindowFocus: false,
    retry: false,
  });

  if (isPending) return <main className="px-6 py-10 text-muted">{vi.compose.loading}</main>;
  if (error || !data) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-10">
        <ErrorNote error={error} />
        <Link to="/" className="btn btn-secondary mt-4">
          {vi.compose.back}
        </Link>
      </main>
    );
  }
  return <EditorProvider key={slug} initial={data} />;
}
