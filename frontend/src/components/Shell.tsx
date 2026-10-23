import { useQuery } from '@tanstack/react-query';
import { NavLink, Outlet } from 'react-router-dom';
import { fetchHealth, type Health } from '../api/client';
import { vi } from '../i18n/vi';

const ITEMS = ['ffmpeg', 'whisper', 'gpu'] as const satisfies readonly (keyof Health)[];

// Tab trên cao: thanh 2 px --accent dưới mục đang chọn (DESIGN-HBT.md mục 10).
const link = ({ isActive }: { isActive: boolean }) =>
  `flex h-16 items-center border-b-2 px-1 text-body font-bold transition-colors duration-[180ms] ease-hbt ${
    isActive ? 'border-accent text-text' : 'border-transparent text-text-muted hover:text-text'
  }`;

/** Chấm trạng thái môi trường: màu kèm chữ ở nhãn đọc màn hình, không chỉ dùng màu. */
function EnvDots() {
  const { data, isError } = useQuery({
    queryKey: ['health'],
    queryFn: () => fetchHealth(),
    retry: false,
    refetchInterval: 30000,
  });
  return (
    <ul aria-label={vi.nav.env} className="hidden items-center gap-3 sm:flex">
      {ITEMS.map((key) => {
        const ok = data?.[key];
        const state =
          isError || data === undefined ? '?' : ok ? vi.health.available : vi.health.missing;
        return (
          <li
            key={key}
            className="flex items-center gap-1.5 text-tiny font-semibold uppercase text-text-muted"
            title={`${vi.health.items[key]}: ${state}`}
          >
            <span
              aria-hidden="true"
              className={`h-2.5 w-2.5 rounded-full ${
                ok ? 'bg-accent' : data ? 'border-2 border-danger' : 'bg-surface-2'
              }`}
            />
            {vi.health.items[key]}
            <span className="sr-only">: {state}</span>
          </li>
        );
      })}
    </ul>
  );
}

export function Shell() {
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-border bg-bg">
        <div className="mx-auto flex h-16 max-w-[1280px] items-center gap-8 px-6">
          <NavLink to="/" className="flex items-center gap-3" aria-label={vi.appName}>
            <img src="/brand/hbt-logo-mark.png" alt="" className="h-10 w-auto" />
            <span className="text-body font-extrabold uppercase tracking-tight">{vi.appName}</span>
          </NavLink>
          <nav aria-label={vi.nav.main} className="flex items-center gap-6">
            <NavLink to="/" end className={link}>
              {vi.nav.projects}
            </NavLink>
            <NavLink to="/settings" className={link}>
              {vi.nav.settings}
            </NavLink>
          </nav>
          <div className="ml-auto">
            <EnvDots />
          </div>
        </div>
      </header>
      <Outlet />
    </div>
  );
}
