import { useCallback, useMemo, useRef, useState, type ReactNode } from 'react';
import { ToastContext, type ToastApi } from '../hooks/toast';
import { vi } from '../i18n/vi';
import { describeError } from '../utils/errors';
import { AlertIcon, CheckIcon, XIcon } from './icons';

interface Item {
  id: number;
  kind: 'info' | 'error';
  message: string;
  hint: string | null;
  retry?: () => void;
}

const SHOW_MS = 3000;
const SHOW_ERROR_MS = 8000; // lỗi có gợi ý cần thời gian đọc hơn 3 giây

/** Toast ở góc dưới phải (DESIGN-HBT.md mục 6). Lỗi có nút "Thử lại" nếu làm được. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Item[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => setItems((xs) => xs.filter((x) => x.id !== id)), []);

  const push = useCallback(
    (item: Omit<Item, 'id'>, ms: number) => {
      const id = nextId.current++;
      setItems((xs) => [...xs.slice(-3), { ...item, id }]);
      setTimeout(() => dismiss(id), ms);
    },
    [dismiss],
  );

  const api: ToastApi = useMemo(
    () => ({
      info: (message) => push({ kind: 'info', message, hint: null }, SHOW_MS),
      error: (error, retry) => {
        const { message, hint } = describeError(error);
        push({ kind: 'error', message, hint, retry }, SHOW_ERROR_MS);
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
            className={`pointer-events-auto flex items-start gap-3 rounded-card p-4 shadow-lg ${
              t.kind === 'error' ? 'bg-danger text-bg' : 'bg-primary text-on-primary'
            }`}
          >
            <span className="mt-0.5 shrink-0">
              {t.kind === 'error' ? <AlertIcon /> : <CheckIcon />}
            </span>
            <div className="min-w-0 flex-1 text-small">
              <p className="font-bold">{t.message}</p>
              {t.hint && <p className="mt-1 opacity-90">{t.hint}</p>}
              {t.retry && (
                <button
                  type="button"
                  className="mt-2 rounded-full border border-current px-3 py-1 font-bold"
                  onClick={() => {
                    dismiss(t.id);
                    t.retry?.();
                  }}
                >
                  {vi.common.retry}
                </button>
              )}
            </div>
            <button
              type="button"
              aria-label={vi.common.closeNotice}
              className="-m-2 flex h-11 w-11 shrink-0 items-center justify-center rounded-full"
              onClick={() => dismiss(t.id)}
            >
              <XIcon size={18} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
