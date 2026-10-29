import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useMemo, useRef, useState } from 'react';
import { Link, Navigate, Outlet, useParams } from 'react-router-dom';
import { api } from '../api/endpoints';
import { isPostv, type PostvProject } from '../api/types';
import { ErrorNote } from '../components/ErrorNote';
import { ArrowLeftIcon } from '../components/icons';
import { PostvSteps } from '../components/postv/PostvSteps';
import { SaveIndicator } from '../components/SaveIndicator';
import { Badge } from '../components/ui/Badge';
import { PostvEditorContext, type PostvEditor } from '../hooks/postvEditor';
import { useAutosave } from '../hooks/useAutosave';
import { vi } from '../i18n/vi';

function PostvEditorProvider({ initial }: { initial: PostvProject }) {
  const queryClient = useQueryClient();
  const [project, setProject] = useState(initial);
  const latest = useRef(initial);
  const [savedCount, setSavedCount] = useState(0);

  const save = useCallback(
    async (value: PostvProject) => {
      await api.savePostv(value.slug, value);
      setSavedCount((n) => n + 1);
      void queryClient.invalidateQueries({ queryKey: ['projects'] });
    },
    [queryClient],
  );
  const { status, error, schedule, flush } = useAutosave(save);

  const update = useCallback(
    (fn: (p: PostvProject) => PostvProject) => {
      const next = fn(latest.current);
      latest.current = next;
      setProject(next);
      schedule(next);
    },
    [schedule],
  );

  const editor = useMemo<PostvEditor>(
    () => ({ project, update, flush, status, saveError: error, savedCount }),
    [project, update, flush, status, error, savedCount],
  );

  const t = vi.postv;
  const done = [
    project.post.text.trim() !== '',
    project.segments.length > 0,
    Boolean(project.voice.file),
    false,
    false,
  ];
  return (
    <PostvEditorContext.Provider value={editor}>
      <main className="mx-auto max-w-[1440px] space-y-4 px-6 py-5">
        <header className="flex min-h-12 flex-wrap items-center gap-3">
          <Link
            to="/postv"
            aria-label={t.back}
            title={t.back}
            className="ui-icon-btn ui-icon-btn-sm"
          >
            <ArrowLeftIcon size={20} />
          </Link>
          <h1 className="line-clamp-1 min-w-0 flex-1 text-title font-extrabold">{project.title}</h1>
          <Badge>{t.badge}</Badge>
          <SaveIndicator status={status} error={error} />
        </header>
        <PostvSteps done={done} />
        <Outlet />
      </main>
    </PostvEditorContext.Provider>
  );
}

/** Khung chung của dự án PostV: tải dự án, tự lưu, thanh 5 bước ở đầu (K-36). */
export function PostvLayout() {
  const { slug = '' } = useParams();
  const t = vi.postv;
  const { data, isPending, error } = useQuery({
    queryKey: ['postv', slug],
    queryFn: () => api.getAnyProject(slug),
    staleTime: Infinity,
    gcTime: 0,
    retry: false,
    refetchOnWindowFocus: false,
  });

  if (isPending)
    return (
      <main className="mx-auto flex max-w-[1440px] items-center gap-3 px-6 py-12 text-muted">
        <span className="ui-spinner" aria-hidden="true" />
        {t.loading}
      </main>
    );
  if (error || !data) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-10">
        <ErrorNote error={error} />
        <Link to="/postv" className="ui-btn ui-btn-soft mt-4">
          {t.back}
        </Link>
      </main>
    );
  }
  if (!isPostv(data)) return <Navigate to={`/p/${slug}`} replace />; // video HBT có trình soạn riêng
  return <PostvEditorProvider key={slug} initial={data} />;
}
