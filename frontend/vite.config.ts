/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    // Chỉ hai file CSS này được đọc thật (test token và luật hiệu năng đọc bằng ?raw); còn lại bỏ qua cho nhanh.
    css: { include: [/styles\/tokens\.css/, /components\/ui\/ui\.css/] },
  },
});
