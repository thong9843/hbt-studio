import { Link, useSearchParams } from 'react-router-dom';
import { HbtCoreWorkspace } from '../components/core/HbtCoreWorkspace';
import { FolderIcon, ZapIcon } from '../components/icons';
import { Badge } from '../components/ui/Badge';
import { Card } from '../components/ui/Card';
import { vi } from '../i18n/vi';

export function HbtCorePage() {
  const [searchParams] = useSearchParams();
  const slugParam = searchParams.get('slug') ?? undefined;

  return (
    <main className="mx-auto max-w-[1280px] space-y-6 px-6 py-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2.5">
            <span className="flex h-10 w-10 items-center justify-center rounded-inner bg-brand text-white">
              <ZapIcon size={22} />
            </span>
            <h1 className="text-h1 font-extrabold uppercase">{vi.hbtCore.title}</h1>
            <Badge tone="red">{vi.nav.hbtCore}</Badge>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link to="/projects" className="ui-btn ui-btn-soft ui-btn-sm">
            <FolderIcon size={18} />
            {vi.nav.projects}
          </Link>
        </div>
      </header>

      <Card as="section" aria-label={vi.hbtCore.title} className="p-6">
        <HbtCoreWorkspace slug={slugParam} active />
      </Card>
    </main>
  );
}
