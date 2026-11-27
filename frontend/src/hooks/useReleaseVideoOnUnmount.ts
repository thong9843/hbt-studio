import { useEffect, type RefObject } from 'react';

/** Giải phóng bộ đệm trình phát và khóa HTTP Range của một phần tử `<video>`. */
export function releaseVideoElement(el: HTMLVideoElement | null | undefined): void {
  if (!el) return;
  try {
    el.pause();
    el.removeAttribute('src');
    el.load();
  } catch {
    // Bỏ qua trong môi trường jsdom hoặc khi phần tử đã tách khỏi DOM
  }
}

/** Tự động giải phóng buffer `<video>` khi component unmount hoặc khóa src thay đổi. */
export function useReleaseVideoOnUnmount(
  ref: RefObject<HTMLVideoElement | null>,
  key?: unknown,
): void {
  useEffect(() => {
    const el = ref.current;
    return () => {
      releaseVideoElement(el);
    };
  }, [ref, key]);
}
