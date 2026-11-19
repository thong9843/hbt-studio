import { useEffect } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { HbtCoreWorkspace } from '../components/core/HbtCoreWorkspace';
import { ArrowLeftIcon, FolderIcon, ZapIcon } from '../components/icons';
import { useStudioWorkspace } from '../hooks/studioWorkspace';
import { vi } from '../i18n/vi';

export function HbtCorePage() {
  const [searchParams] = useSearchParams();
  const slugParam = searchParams.get('slug') ?? undefined;
  const ws = useStudioWorkspace();
  const setStudioMode = ws?.setStudioMode;

  useEffect(() => {
    setStudioMode?.(true);
    return () => {
      setStudioMode?.(false);
    };
  }, [setStudioMode]);

  return (
    <main className="flex min-h-screen w-full flex-col bg-bg text-text">
      <header className="flex min-h-[56px] flex-wrap items-center justify-between gap-3 border-b border-line bg-card px-4 py-2">
        <div className="flex items-center gap-2.5">
          <Link
            to="/"
            aria-label={vi.studioShell.backToHome}
            title={vi.studioShell.backToHome}
            className="ui-icon-btn ui-icon-btn-sm border border-line bg-soft text-text"
          >
            <ArrowLeftIcon size={15} />
          </Link>
          <span className="inline-flex items-center gap-1 rounded-pill bg-[var(--accent-soft)] px-2.5 py-0.5 text-tiny font-bold text-[var(--on-accent-soft)]">
            <ZapIcon size={13} />
            {vi.nav.hbtCore}
          </span>
          <h1 className="truncate text-body font-bold tracking-tight text-text">
            {vi.hbtCore.title}
          </h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
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
