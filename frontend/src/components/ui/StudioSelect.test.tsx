import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { WatermarkControl } from '../WatermarkControl';
import { SegmentedControl } from './SegmentedControl';
import { StudioSelect } from './StudioSelect';

import assetHubSrc from '../../pages/AssetHubPage.tsx?raw';
import chattingEditorSrc from '../../pages/chatting/ChattingEditor.tsx?raw';
import chattingHomeSrc from '../../pages/chatting/ChattingHome.tsx?raw';
import hbtCoreSrc from '../core/HbtCoreWorkspace.tsx?raw';
import postvQuickSrc from '../../pages/PostvQuickPage.tsx?raw';
import settingsSrc from '../../pages/SettingsPage.tsx?raw';
import stickvSrc from '../../pages/StickvPage.tsx?raw';
import watermarkSrc from '../WatermarkControl.tsx?raw';

vi.mock('../../api/endpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/endpoints')>();
  return {
    ...actual,
    api: {
      ...actual.api,
      getAppSettings: vi.fn().mockResolvedValue({
        default_fps: 60,
        theme: { primary: '#0f172a', accent: '#facc15' },
        whisper_model: 'auto',
        whisper_timeout_seconds: 900,
        watermark: {
          enabled: true,
          mode: 'both',
          text: '@HayBietTuot',
          logo_path: 'brand/hbt-logo-mark.png',
          position: 'bottom-right',
          opacity: 0.4,
        },
      }),
      saveAppSettings: vi.fn().mockImplementation(async (s) => s),
    },
  };
});

function SelectHarness() {
  const [val, setVal] = useState('science');
  return (
    <div>
      <StudioSelect
        label="Chủ đề thử nghiệm"
        aria-label="Chủ đề thử nghiệm"
        value={val}
        onChange={setVal}
        options={[
          { value: 'science', label: 'Khoa học', description: 'Tư duy logic' },
          { value: 'history', label: 'Lịch sử', description: 'Dòng thời gian' },
          { value: 'mystery', label: 'Bí ẩn' },
        ]}
      />
      <button type="button">Vùng bên ngoài</button>
    </div>
  );
}

describe('StudioSelect & Pro Craft UI Controls', () => {
  it('opens/closes on click, supports ArrowUp/Down, Enter, Escape and outside click', () => {
    render(<SelectHarness />);

    const trigger = screen.getByRole('combobox', { name: 'Chủ đề thử nghiệm' });
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(trigger).toHaveAttribute('data-value', 'science');

    // Mở bằng click chuột
    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    expect(screen.getByText('Tư duy logic')).toBeInTheDocument();

    // Đóng bằng phím Escape
    fireEvent.keyDown(trigger, { key: 'Escape' });
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();

    // Mở bằng phím ArrowDown, di chuyển xuống 'Lịch sử', chọn bằng Enter
    fireEvent.keyDown(trigger, { key: 'ArrowDown' });
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    fireEvent.keyDown(trigger, { key: 'ArrowDown' });
    fireEvent.keyDown(trigger, { key: 'Enter' });
    expect(trigger).toHaveAttribute('data-value', 'history');
    expect(trigger).toHaveAttribute('aria-expanded', 'false');

    // Mở lại rồi di chuyển ngược lên 'Khoa học' bằng ArrowUp và đóng khi click ngoài
    fireEvent.click(trigger);
    fireEvent.keyDown(trigger, { key: 'ArrowUp' });
    fireEvent.mouseDown(screen.getByRole('button', { name: 'Vùng bên ngoài' }));
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(trigger).toHaveAttribute('data-value', 'history');
  });

  it('slides SegmentedControl thumb via transform translateX', () => {
    function SegHarness() {
      const [aspect, setAspect] = useState<'9:16' | '16:9'>('9:16');
      return (
        <SegmentedControl
          aria-label="Tỷ lệ khung"
          value={aspect}
          onChange={setAspect}
          options={[
            { value: '9:16', label: '9:16' },
            { value: '16:9', label: '16:9' },
          ]}
        />
      );
    }

    const { container } = render(<SegHarness />);
    const thumb = container.querySelector('.ui-segmented-thumb') as HTMLElement;
    expect(thumb).toBeTruthy();
    expect(thumb.style.transform).toBe('translateX(0%)');

    fireEvent.click(screen.getByRole('radio', { name: '16:9' }));
    expect(thumb.style.transform).toBe('translateX(100%)');
  });

  it('renders WatermarkControl with adaptive token surfaces (no hardcoded light indigo gradient)', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container } = render(
      <QueryClientProvider client={qc}>
        <WatermarkControl />
      </QueryClientProvider>,
    );

    expect(await screen.findByText(/Logo \+ @HayBietTuot · Góc dưới phải/i)).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'Watermark bản quyền' })).toBeInTheDocument();

    // Không dùng nền sáng cứng #EEF2FF / #C7D2FE / bg-indigo-600 gây vỡ Dark Mode
    expect(watermarkSrc).not.toMatch(/#EEF2FF|#F5F3FF|#C7D2FE|bg-indigo-600/);
    expect(container.querySelector('.ui-wm-badge')).toBeTruthy();

    // Mở rộng dùng StudioSelect thay vì native <select>
    fireEvent.click(screen.getByRole('button', { name: 'Tùy chỉnh' }));
    expect(screen.getByRole('combobox', { name: 'Kiểu Watermark' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Vị trí Watermark' })).toBeInTheDocument();
    expect(container.querySelectorAll('select')).toHaveLength(0);
  });

  it('guarantees zero raw <select> tags across all primary Studio pages', () => {
    const studioSources: [string, string][] = [
      ['StickvPage.tsx', stickvSrc],
      ['HbtCoreWorkspace.tsx', hbtCoreSrc],
      ['PostvQuickPage.tsx', postvQuickSrc],
      ['ChattingHome.tsx', chattingHomeSrc],
      ['ChattingEditor.tsx', chattingEditorSrc],
      ['SettingsPage.tsx', settingsSrc],
      ['WatermarkControl.tsx', watermarkSrc],
      ['AssetHubPage.tsx', assetHubSrc],
    ];

    for (const [name, src] of studioSources) {
      expect(src, `${name} vẫn còn thẻ <select> gốc`).not.toMatch(/<select[\s>]/);
      expect(src, `${name} vẫn dùng wrapper <Select> gốc`).not.toMatch(/<Select[\s>]/);
    }
  });
});
