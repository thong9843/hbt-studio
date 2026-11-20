import { Link, useSearchParams } from 'react-router-dom';
import { HbtCoreWorkspace } from '../components/core/HbtCoreWorkspace';
import { ArrowLeftIcon, FolderIcon, ZapIcon } from '../components/icons';
import { vi } from '../i18n/vi';

export function HbtCorePage() {
  const [searchParams] = useSearchParams();
  const slugParam = searchParams.get('slug') ?? undefined;

  return (
    <main className="flex min-h-screen w-full flex-col bg-bg text-text">
      <header className="flex h-[56px] shrink-0 items-center justify-between gap-3 border-b border-line bg-card px-3.5">
        <div className="flex min-w-0 items-center gap-2">
          <Link
            to="/"
            aria-label={vi.studioShell.backToHome}
            title={vi.studioShell.backToHome}
            className="ui-icon-btn ui-icon-btn-sm border border-line bg-soft text-text"
          >
            <ArrowLeftIcon size={15} />
          </Link>
          <span className="inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-pill bg-[var(--accent-soft)] px-2.5 py-1 text-[13px] font-semibold text-[var(--on-accent-soft)]">
            <ZapIcon size={13} />
            {vi.nav.hbtCore}
          </span>
          <span className="inline-flex shrink-0 items-center gap-1.5 rounded-pill bg-soft px-2 py-0.5 text-[11px] font-semibold text-muted">
            <span className="h-1.5 w-1.5 rounded-full bg-ok" aria-hidden="true" />
            {vi.studioShell.savedBadge}
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Link to="/library" className="ui-btn ui-btn-soft ui-btn-sm">
            <FolderIcon size={15} />
            {vi.nav.library}
          </Link>
        </div>
      </header>

      <div className="flex-1 p-4 lg:p-5">
        <HbtCoreWorkspace slug={slugParam} active />
      </div>
    </main>
  );
}
