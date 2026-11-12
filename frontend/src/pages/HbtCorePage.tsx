import { Link, useSearchParams } from 'react-router-dom';
import { HbtCoreWorkspace } from '../components/core/HbtCoreWorkspace';
import { FolderIcon, ZapIcon } from '../components/icons';
import { Badge } from '../components/ui/Badge';
import { vi } from '../i18n/vi';

export function HbtCorePage() {
  const [searchParams] = useSearchParams();
  const slugParam = searchParams.get('slug') ?? undefined;

  return (
    <main className="mx-auto max-w-[1440px] space-y-6 px-6 py-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-inner bg-gradient-to-br from-indigo-500 via-violet-500 to-amber-500 text-white shadow-sm">
            <ZapIcon size={20} />
          </span>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-h1 font-extrabold uppercase tracking-tight">
                {vi.hbtCore.title}
              </h1>
              <Badge tone="yel">{vi.nav.hbtCore}</Badge>
            </div>
            <p className="text-small text-muted">{vi.hbtCore.lead}</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link to="/library" className="ui-btn ui-btn-soft ui-btn-sm">
            <FolderIcon size={16} />
            {vi.nav.library}
          </Link>
        </div>
      </header>

      <HbtCoreWorkspace slug={slugParam} active />
    </main>
  );
}
