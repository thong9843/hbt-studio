import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { ToastContext, type ToastApi } from '../hooks/toast';
import { vi } from '../i18n/vi';
import { describeError } from '../utils/errors';
import { AlertIcon, CheckIcon, XIcon } from './icons';
import { IconButton } from './ui/IconButton';
import './ui/ui.css';

interface Item {
  id: number;
  kind: 'info' | 'error';
  message: string;
  hint: string | null;
  action?: { label: string; run: () => void };
}

export const TOAST_MS = 3000;
export const TOAST_UNDO_MS = 8000; // thông báo có Hoàn tác cần thời gian bấm
export const TOAST_ERROR_MS = 8000; // lỗi có gợi ý cần thời gian đọc hơn 3 giây

/** Thông báo ở góc dưới phải: trượt lên 8 px + hiện 200 ms (DESIGN-HBT.md mục 6). */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Item[]>([]);
  const nextId = useRef(1);
  const timers = useRef(new Set<ReturnType<typeof setTimeout>>());

  useEffect(() => {
    const live = timers.current;
    return () => live.forEach(clearTimeout);
  }, []);

  const dismiss = useCallback((id: number) => setItems((xs) => xs.filter((x) => x.id !== id)), []);

  const push = useCallback(
    (item: Omit<Item, 'id'>, ms: number) => {
      const id = nextId.current++;
      setItems((xs) => [...xs.slice(-3), { ...item, id }]);
      const t = setTimeout(() => {
        timers.current.delete(t);
        dismiss(id);
      }, ms);
      timers.current.add(t);
    },
    [dismiss],
  );

  const api: ToastApi = useMemo(
    () => ({
      info: (message, options) =>
        push(
          {
            kind: 'info',
            message,
            hint: null,
            action: options?.undo ? { label: vi.common.undo, run: options.undo } : undefined,
          },
          options?.undo ? TOAST_UNDO_MS : TOAST_MS,
        ),
      error: (error, retry) => {
        const { message, hint } = describeError(error);
        push(
          {
            kind: 'error',
            message,
            hint,
            action: retry ? { label: vi.common.retry, run: retry } : undefined,
          },
          TOAST_ERROR_MS,
        );
      },
    }),
    [push],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="pointer-events-none fixed bottom-6 right-6 z-50 flex w-[min(24rem,calc(100vw-3rem))] flex-col gap-2">
        {items.map((t) => (
          <div
            key={t.id}
            role={t.kind === 'error' ? 'alert' : 'status'}
            className={`ui-toast pointer-events-auto ${t.kind === 'error' ? 'ui-toast-error' : ''}`}
          >
            <span className="mt-0.5 shrink-0">
              {t.kind === 'error' ? <AlertIcon /> : <CheckIcon />}
            </span>
            <div className="min-w-0 flex-1 text-small">
              <p className="font-bold">{t.message}</p>
              {t.hint && <p className="mt-1 opacity-90">{t.hint}</p>}
              {t.action && (
                <button
                  type="button"
                  className="mt-2 min-h-9 rounded-full border border-current px-4 font-bold"
                  onClick={() => {
                    dismiss(t.id);
                    t.action?.run();
                  }}
                >
                  {t.action.label}
                </button>
              )}
            </div>
            <IconButton
              label={vi.common.closeNotice}
              small
              className="-m-1 text-current"
              onClick={() => dismiss(t.id)}
            >
              <XIcon size={18} />
            </IconButton>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
