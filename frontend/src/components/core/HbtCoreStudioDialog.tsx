import { vi } from '../../i18n/vi';
import { Dialog } from '../ui/Dialog';
import { HbtCoreWorkspace } from './HbtCoreWorkspace';

interface Props {
  open: boolean;
  onClose: () => void;
  /** Nếu mở từ trong một dự án đang có sẵn (`/p/:slug`). */
  slug?: string;
}

export function HbtCoreStudioDialog({ open, onClose, slug }: Props) {
  return (
    <Dialog open={open} onClose={onClose} title={vi.hbtCore.title} className="!max-w-[920px]">
      <div className="max-h-[75vh] overflow-y-auto pr-1">
        <HbtCoreWorkspace slug={slug} onClose={onClose} active={open} />
      </div>
    </Dialog>
  );
}
