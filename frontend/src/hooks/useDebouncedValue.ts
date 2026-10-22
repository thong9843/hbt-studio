import { useEffect, useState } from 'react';

/** Giá trị trễ `delayMs` sau lần đổi cuối (xem trước cảnh: 600 ms sau khi ngừng gõ). */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(id);
  }, [value, delayMs]);
  return debounced;
}
