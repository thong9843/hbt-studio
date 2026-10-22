import type { SaveStatus } from '../hooks/useAutosave';
import { vi } from '../i18n/vi';
import { AlertIcon, CheckIcon } from './icons';

const STYLE: Record<SaveStatus, string> = {
  idle: 'chip-muted',
  dirty: 'chip-warn',
  saving: 'chip-warn',
  saved: 'chip-ok',
  error: 'chip-danger',
};

/** Chỉ báo "Đã lưu" (IMPLEMENT.md mục 10.2). */
export function SaveIndicator({ status, error }: { status: SaveStatus; error?: string | null }) {
  const text = vi.compose.saveStatus[status];
  return (
    <span role="status" aria-live="polite" className="inline-flex items-center gap-2">
      {text && (
        <span className={`chip ${STYLE[status]}`}>
          {status === 'saving' && <span className="spinner h-3 w-3" aria-hidden="true" />}
          {status === 'saved' && <CheckIcon size={14} />}
          {status === 'error' && <AlertIcon size={14} />}
          {text}
        </span>
      )}
      {status === 'error' && error && <span className="text-small text-danger">{error}</span>}
    </span>
  );
}
