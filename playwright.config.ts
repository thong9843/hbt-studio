import { defineConfig } from '@playwright/test';

// Chỉ chạy trên máy cá nhân (npm run e2e); không có trong CI.
// Dùng trình duyệt Edge có sẵn trên Windows nên không phải tải trình duyệt.
export default defineConfig({
  testDir: 'e2e',
  timeout: 60_000,
  reporter: 'list',
  use: { baseURL: 'http://127.0.0.1:5173', channel: 'msedge' },
  webServer: {
    command: 'npm run dev',
    url: 'http://127.0.0.1:5173',
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
