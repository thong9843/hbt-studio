import { NavLink, Outlet } from 'react-router-dom';
import { vi } from '../i18n/vi';

const link = ({ isActive }: { isActive: boolean }) =>
  `rounded-full px-4 py-1.5 text-sm font-bold transition ${
    isActive ? 'bg-fg text-bg' : 'text-fg hover:bg-surface'
  }`;

export function Shell() {
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-border bg-bg/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1400px] items-center gap-6 px-6 py-3">
          <NavLink to="/" className="flex items-center gap-3" aria-label={vi.appName}>
            <img src="/brand/hbt-logo-mark.png" alt="" className="h-10 w-auto" />
            <span className="text-lg font-extrabold uppercase tracking-tight">{vi.appName}</span>
          </NavLink>
          <nav aria-label={vi.nav.main} className="ml-auto flex items-center gap-2">
            <NavLink to="/" end className={link}>
              {vi.nav.projects}
            </NavLink>
            <NavLink to="/settings" className={link}>
              {vi.nav.settings}
            </NavLink>
          </nav>
        </div>
      </header>
      <Outlet />
    </div>
  );
}
