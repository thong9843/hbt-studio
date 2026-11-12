import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { renderWithProviders } from '../test/render';
import { WaterfallProgress, type WaterfallStep } from './WaterfallProgress';

describe('WaterfallProgress (src/shared)', () => {
  it('renders 4 steps with status badges and toggles dropdown log on click', async () => {
    const user = userEvent.setup();
    const steps: WaterfallStep[] = [
      {
        id: 'script',
        icon: '📝',
        title: 'Khởi tạo kịch bản (Gemini API)',
        state: 'done',
        logs: ['Đã sinh 8 phân cảnh thành công'],
      },
      {
        id: 'voice',
        icon: '🎙️',
        title: 'Sinh giọng thuyết minh (VieNeu-TTS từng câu)',
        state: 'running',
        badgeText: '3/10 câu',
        logs: ['Đang đọc phân đoạn 3/10'],
      },
      {
        id: 'assets',
        icon: '🎨',
        title: 'Chuẩn bị hình ảnh & Sticker',
        state: 'waiting',
        logs: [],
      },
      {
        id: 'render',
        icon: '🎬',
        title: 'Render video hoàn chỉnh (FFmpeg timeline 9:16)',
        state: 'waiting',
        logs: [],
      },
    ];

    renderWithProviders(
      <WaterfallProgress title="Tiến trình tự động HBT Core" overallPercent={35} steps={steps} />,
    );

    expect(screen.getByText('35%')).toBeVisible();
    expect(screen.getByText('3/10 câu')).toBeVisible();
    expect(screen.getByText('Xong')).toBeVisible();
    expect(screen.getByText('Đang chạy')).toBeVisible();

    // Log ẩn mặc định
    expect(screen.queryByText('Đang đọc phân đoạn 3/10')).toBeNull();

    // Click mở dropdown của Bước 2
    await user.click(screen.getByRole('button', { name: /Sinh giọng thuyết minh/ }));
    expect(screen.getByText('Đang đọc phân đoạn 3/10')).toBeVisible();
  });
});
