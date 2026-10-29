import { useQuery } from '@tanstack/react-query';
import { Link, Navigate, useParams } from 'react-router-dom';
import { api } from '../api/endpoints';
import { isPostv } from '../api/types';
import { ErrorNote } from '../components/ErrorNote';
import { ArrowLeftIcon } from '../components/icons';
import { Badge } from '../components/ui/Badge';
import { Card } from '../components/ui/Card';
import { vi } from '../i18n/vi';

/**
 * Màn PostV. Mốc PV1 chỉ mở được dự án và hiện 5 bước ("sắp có"); các bước làm ở PV2–PV6
 * (docs/postv/IMPLEMENT-POSTV.md mục 7).
 */
export function PostvPage() {
  const { slug = '' } = useParams();
  const t = vi.postv;
  const { data, isPending, error } = useQuery({
    queryKey: ['postv', slug],
    queryFn: () => api.getAnyProject(slug),
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
        <Link to="/projects" className="ui-btn ui-btn-soft mt-4">
          {t.back}
        </Link>
      </main>
    );
  }
  if (!isPostv(data)) return <Navigate to={`/p/${slug}`} replace />; // video HBT có trình soạn riêng

  return (
    <main className="mx-auto max-w-[1440px] space-y-6 px-6 py-8">
      <div className="flex flex-wrap items-center gap-3">
        <Link to="/projects" className="ui-btn ui-btn-soft">
          <ArrowLeftIcon size={18} />
          {t.back}
        </Link>
        <h1 className="line-clamp-2 min-w-0 flex-1 text-title font-extrabold">{data.title}</h1>
        <Badge>{t.badge}</Badge>
      </div>
      <Card as="section" aria-label={t.stepsLabel} className="space-y-4">
        <ol className="grid gap-3 md:grid-cols-5">
          {t.steps.map((label, i) => (
            <li key={label} className="ui-inner flex items-center gap-3 p-3">
              <span className="num flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-soft text-small font-bold">
                {i + 1}
              </span>
              <span className="min-w-0 flex-1 text-small font-semibold">{label}</span>
              <Badge tone="yel">{t.soon}</Badge>
            </li>
          ))}
        </ol>
        <p className="text-small text-muted">{t.soonNote}</p>
      </Card>
    </main>
  );
}
