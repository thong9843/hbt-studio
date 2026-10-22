import { useCallback, useEffect, useRef, useState } from 'react';

export type SaveStatus = 'idle' | 'dirty' | 'saving' | 'saved' | 'error';

/**
 * Lưu tự động có debounce (IMPLEMENT.md mục 10.2: 1 s). `schedule(value)` ghi nhớ giá trị mới nhất
 * và hẹn lưu; `flush()` lưu ngay (dùng trước khi tải file / dựng video). Các lần lưu chạy tuần tự,
 * lần lưu lỗi giữ lại giá trị để thử lại. Rời trang thì lưu nốt phần đang chờ.
 */
export function useAutosave<T>(save: (value: T) => Promise<unknown>, delayMs = 1000) {
  const [status, setStatus] = useState<SaveStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const pending = useRef<{ value: T } | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const chain = useRef<Promise<void>>(Promise.resolve());
  const saveRef = useRef(save);

  useEffect(() => {
    saveRef.current = save;
  }, [save]);

  const run = useCallback((): Promise<void> => {
    timer.current = undefined;
    const job = pending.current;
    if (!job) return chain.current;
    pending.current = null;
    setStatus('saving');
    chain.current = chain.current.then(async () => {
      try {
        await saveRef.current(job.value);
        setError(null);
        setStatus(pending.current ? 'dirty' : 'saved');
      } catch (e) {
        pending.current ??= job; // giữ lại để thử lại, trừ khi đã có giá trị mới hơn
        setError(e instanceof Error ? e.message : String(e));
        setStatus('error');
      }
    });
    return chain.current;
  }, []);

  const schedule = useCallback(
    (value: T) => {
      pending.current = { value };
      setStatus('dirty');
      clearTimeout(timer.current);
      timer.current = setTimeout(() => void run(), delayMs);
    },
    [delayMs, run],
  );

  const flush = useCallback(() => {
    clearTimeout(timer.current);
    return run();
  }, [run]);

  useEffect(
    () => () => {
      clearTimeout(timer.current);
      void run();
    },
    [run],
  );

  const hasPending = useCallback(() => pending.current !== null, []);

  return { status, error, schedule, flush, hasPending };
}
