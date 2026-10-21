export const vi = {
  appName: 'HBT Studio',
  health: {
    title: 'Trạng thái môi trường',
    loading: 'Đang kiểm tra…',
    unreachable: 'Không kết nối được máy chủ. Hãy chạy npm run dev.',
    ready: 'Sẵn sàng dựng video',
    notReady: 'Chưa dựng được video',
    missingList: 'FFmpeg thiếu:',
    recheck: 'Kiểm tra lại',
    items: {
      ffmpeg: 'FFmpeg',
      whisper: 'Whisper',
      gpu: 'GPU',
    },
    available: 'có',
    missing: 'thiếu',
  },
} as const;
