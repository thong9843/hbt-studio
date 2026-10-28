import { vi } from '../i18n/vi';
import { PlusIcon } from './icons';
import { Button } from './ui/Button';

/** Màn trống (chưa có dự án): hero, một câu, nút Tạo video và 3 bước. Dùng ở Trang chủ và Dự án. */
export function EmptyProjects({ onCreate }: { onCreate: () => void }) {
  const t = vi.projects.empty;
  return (
    <div className="flex flex-col items-center gap-8 rounded-card bg-card px-6 py-16 text-center">
      <img src="/brand/hbt-logo-mark.png" alt="" className="h-20 w-auto" />
      <h2 className="text-hero font-extrabold uppercase">
        <span className="block">{t.heroLine1}</span>
        <span className="block">{t.heroLine2}</span>
      </h2>
      <p className="text-body text-muted">{t.lead}</p>
      <Button tone="brand" size="lg" icon={<PlusIcon />} onClick={onCreate}>
        {t.create}
      </Button>
      <ol className="mt-4 grid w-full max-w-[720px] grid-cols-1 gap-3 min-[640px]:grid-cols-3">
        {t.steps.map((step, i) => (
          <li key={step} className="ui-inner flex items-center gap-3 p-4 text-left">
            <span className="num flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary text-small font-bold text-on-primary">
              {i + 1}
            </span>
            <span className="text-small font-bold">{step}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
