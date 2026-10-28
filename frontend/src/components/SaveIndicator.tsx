import type { SaveStatus } from '../hooks/useAutosave';
import { vi } from '../i18n/vi';
import { AlertIcon, CheckIcon } from './icons';
import { Badge, type BadgeTone } from './ui/Badge';

const TONE: Record<SaveStatus, BadgeTone> = {
  idle: 'neutral',
  dirty: 'yel',
  saving: 'yel',
  saved: 'ok',
  error: 'danger',
};

/** Chỉ báo "Đã lưu" (IMPLEMENT.md mục 10.2). Luôn có chữ; màu chỉ là phụ. */
export function SaveIndicator({ status, error }: { status: SaveStatus; error?: string | null }) {
  const text = vi.compose.saveStatus[status];
  return (
    <span role="status" aria-live="polite" className="inline-flex items-center gap-2">
      {text && (
        <Badge tone={TONE[status]}>
          {status === 'saving' && <span className="ui-spinner !h-3 !w-3" aria-hidden="true" />}
          {status === 'saved' && <CheckIcon size={14} />}
          {status === 'error' && <AlertIcon size={14} />}
          {text}
        </Badge>
      )}
      {status === 'error' && error && <span className="text-small text-danger">{error}</span>}
    </span>
  );
}
