/** Giải phóng mọi kết nối HTTP Range từ các thẻ <video> trước khi xóa file trên Windows. */
export function releaseVideoElementLocks(urlPrefix?: string): void {
  if (typeof document === 'undefined') return;
  const videos = document.querySelectorAll('video');
  for (const video of videos) {
    const src = video.currentSrc || video.getAttribute('src') || '';
    if (!urlPrefix || src.includes(urlPrefix)) {
      try {
        video.pause();
        video.removeAttribute('src');
        video.load();
      } catch {
        // Bỏ qua trong môi trường jsdom hoặc DOM đã gỡ
      }
    }
  }
}
