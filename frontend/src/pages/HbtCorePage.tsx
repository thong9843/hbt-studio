import { Link, useSearchParams } from 'react-router-dom';
import { HbtCoreWorkspace } from '../components/core/HbtCoreWorkspace';
import { FolderIcon, ZapIcon } from '../components/icons';
import { Badge } from '../components/ui/Badge';
import { vi } from '../i18n/vi';

export function HbtCorePage() {
  const [searchParams] = useSearchParams();
  const slugParam = searchParams.get('slug') ?? undefined;

  return (
    <main className="w-full max-w-full space-y-6 px-6 py-7 lg:px-8">
      <header className="flex flex-wrap items-center justify-between gap-4 rounded-card border border-line bg-card/85 p-5 shadow-card backdrop-blur-sm">
        <div className="flex items-center gap-3.5">
          <span className="flex h-11 w-11 items-center justify-center rounded-inner bg-gradient-to-br from-[#F43F5E] to-[#E11D48] text-white shadow-sm">
            <ZapIcon size={22} />
          </span>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-h1 font-extrabold tracking-tight text-text">
                {vi.hbtCore.title}
              </h1>
              <Badge tone="core">{vi.nav.hbtCore}</Badge>
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
