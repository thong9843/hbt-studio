import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { useRef } from 'react';
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api/endpoints';
import { stickvApi } from '../api/stickv';
import { GlobalJobDock } from '../components/layout/GlobalJobDock';
import { RenderJobProvider } from '../components/RenderJobProvider';
import { ToastProvider } from '../components/Toast';
import { resetActiveStreams } from '../hooks/useJob';
import { FakeEventSource } from '../test/fakes';
import { StickvPage } from './StickvPage';

vi.mock('../api/stickv', () => ({
  stickvApi: {
    list: vi.fn().mockResolvedValue({
      items: [
        {
          slug: 'demo-stickv',
          title: 'Video Demo StickV',
          topic: 'science',
          aspect: '9:16',
          theme: 'cream',
          fps: 30,
          voice_id: 'vienneu_default',
          music_mood: 'science',
          gemini_model: 'gemini-2.5-flash',
          target_minutes: 1,
          beats: [
            {
              id: 'b001',
              chapter: 1,
              narration: 'Đây là beat mở đầu.',
              pose: 'explain',
              facing: 'right',
              motion: 'bounce',
              sfx_tag: 'whoosh',
              board_type: 'bullets',
              board_title: 'Mở đầu',
              board_data: { items: ['Ý 1'] },
              media_path: '',
              duration_sec: 2.5,
            },
          ],
          created_at: '2026-11-17T00:00:00Z',
          updated_at: '2026-11-17T00:00:00Z',
        },
      ],
      gemini_models: [
        { id: 'gemini-3.1-flash-lite', name: 'Gemini 3.1 Flash Lite (Mặc định / 500 RPD)' },
        { id: 'gemini-3.8-flash', name: 'Gemini 3.8 Flash (Nhanh)' },
      ],
      default_model: 'gemini-3.1-flash-lite',
      director_prompt: 'Prompt Đạo diễn 5 chặng',
    }),
    save: vi.fn(),
    generate: vi.fn(),
    remove: vi.fn(),
    render: vi.fn(),
  },
}));

vi.mock('../api/endpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/endpoints')>();
  return {
    ...actual,
    api: {
      ...actual.api,
      listAssetHub: vi.fn().mockResolvedValue({
        category: 'stickman',
        items: [
          {
            id: 'custom-flow',
            name: 'flow_hero.png',
            category: 'stickman',
            kind: 'image',
            size: 1200,
            modified_at: '2026-11-17T00:00:00Z',
            url: '/api/asset-hub/files/stickman/flow_hero.png',
            title: 'Flow Hero',
          },
        ],
      }),
      listVoices: vi.fn().mockResolvedValue({
        default: 'Adam bựa',
        voices: [
          { id: 'Adam bựa', label: 'Adam bựa' },
          { id: 'Thanh Bình', label: 'Thanh Bình' },
        ],
      }),
      listActiveJobs: vi.fn().mockResolvedValue([]),
      listJobs: vi.fn().mockResolvedValue([]),
    },
  };
});

beforeEach(() => {
  resetActiveStreams();
  FakeEventSource.instances = [];
  vi.stubGlobal('EventSource', FakeEventSource);
});

afterEach(() => {
  resetActiveStreams();
  vi.unstubAllGlobals();
});

describe('StickvPage', () => {
  it('renders minimalist Topbar with single Export button, auto-collapses AI creator when >= 1 beat, and strictly separates 4 Inspector tabs without duplicate dropdowns', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <ToastProvider>
            <RenderJobProvider>
              <StickvPage />
            </RenderJobProvider>
          </ToastProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByDisplayValue('Đây là beat mở đầu.')).toBeInTheDocument();

    // 1. Topbar tối giản: không còn tiêu đề dài thừa và không còn nút Xem nhanh / Xuất bản đẹp / Xóa đứng lộ trên Topbar
    const banner = screen.getByRole('banner');
    expect(within(banner).queryByText(/Xưởng Video Người Que/i)).toBeNull();
    expect(within(banner).queryByRole('button', { name: /Xem nhanh/i })).toBeNull();
    expect(within(banner).queryByRole('button', { name: /Xuất bản đẹp/i })).toBeNull();
    expect(within(banner).queryByRole('button', { name: /^Xóa$/i })).toBeNull();
    expect(within(banner).getByRole('button', { name: 'Xuất video' })).toBeInTheDocument();
    expect(within(banner).getByRole('button', { name: 'Tùy chọn dự án' })).toBeInTheDocument();

    // 2. 4 Tab Inspector rút gọn vừa khít cột 376px, không cắt chữ
    const tablist = screen.getByRole('tablist', { name: 'Nhóm công cụ Studio' });
    const tabs = within(tablist).getAllByRole('tab');
    expect(tabs.map((t) => t.textContent?.replace(/\d+$/, '').trim())).toEqual([
      'Kịch bản',
      'Hình ảnh',
      'Âm thanh',
      'Kiểm tra',
    ]);

    // 3. Khung Khởi tạo Kịch bản AI tự động gấp gọn khi dự án đã có >= 1 beat
    const accordionBtn = screen.getByRole('button', {
      name: /Tạo kịch bản AI mới \/ Dán JSON/i,
    });
    expect(accordionBtn).toHaveAttribute('aria-expanded', 'false');

    // Tab Kịch bản tuyệt đối KHÔNG chứa 4 dropdown hình ảnh (Dáng, Tương tác, Bảng, Cam)
    expect(screen.queryByRole('combobox', { name: 'Dáng người que' })).toBeNull();
    expect(screen.queryByRole('combobox', { name: 'Tương tác sân khấu' })).toBeNull();
    expect(screen.queryByRole('combobox', { name: 'Loại bảng minh họa' })).toBeNull();
    expect(screen.queryByRole('combobox', { name: 'Góc máy ảo' })).toBeNull();

    // Bấm mở Accordion tạo kịch bản AI
    fireEvent.click(accordionBtn);
    expect(accordionBtn).toHaveAttribute('aria-expanded', 'true');
    const modelSelect = screen.getByRole('combobox', { name: 'Chọn model Gemini' });
    expect(modelSelect).toHaveAttribute('data-value', 'gemini-3.1-flash-lite');
    fireEvent.click(screen.getByRole('tab', { name: 'Dán JSON (0 Token)' }));
    expect(screen.getByRole('button', { name: /Copy Prompt Đạo diễn/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'Dán Lời thoại' }));
    expect(screen.getByRole('button', { name: /Tách lời thoại thành Beat/i })).toBeInTheDocument();

    // 4. Chuyển sang Tab Hình ảnh: hiển thị đầy đủ Dáng, Biểu cảm, Góc máy, Loại bảng, Tương tác, Bối cảnh, Màu, Diễn hoạt
    fireEvent.click(within(tablist).getByRole('tab', { name: 'Hình ảnh' }));
    const poseSelect = screen.getByRole('combobox', { name: 'Dáng người que' });
    fireEvent.click(poseSelect);
    expect(screen.getByRole('option', { name: 'Dáng: Flow Hero' })).toBeInTheDocument();
    fireEvent.keyDown(poseSelect, { key: 'Escape' });
    expect(screen.getByRole('combobox', { name: 'Biểu cảm khuôn mặt' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Góc máy ảo' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Loại bảng minh họa' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Tương tác sân khấu' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Bối cảnh sân khấu' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Chế độ diễn hoạt' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Chủ đề màu' })).toBeInTheDocument();
    // Tab Hình ảnh không lặp lại dropdown SFX của tab Âm thanh
    expect(screen.queryByRole('combobox', { name: 'Âm thanh SFX' })).toBeNull();

    // 5. Chuyển sang Tab Âm thanh: hiển thị Giọng đọc VieNeu, Tâm trạng nhạc, Nhóm nhạc, SFX
    fireEvent.click(within(tablist).getByRole('tab', { name: 'Âm thanh' }));
    const voiceSelect = await screen.findByRole('combobox', { name: 'Chọn giọng đọc VieNeu' });
    expect(voiceSelect).toHaveAttribute('data-value', 'Thanh Bình');
    expect(screen.getByRole('combobox', { name: 'Tâm trạng nhạc' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Nhóm nhạc' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Âm thanh SFX' })).toBeInTheDocument();

    // 6. Chuyển tỷ lệ 9:16 | 16:9 trên Topbar
    fireEvent.click(within(banner).getByRole('button', { name: '16:9' }));
    expect(screen.getByText(/1920 × 1080 \(16:9\)/)).toBeInTheDocument();
  });

  it('hides GlobalJobDock while on /stickv, shows it when navigating away, and re-renders StickvPage 0 times during 1% -> 100% progress updates', async () => {
    vi.mocked(stickvApi.save).mockResolvedValue({ project: {} as never });
    vi.mocked(stickvApi.render).mockResolvedValue({
      job_id: 'sv-job-99',
      slug: 'demo-stickv',
      preview: false,
    });
    vi.mocked(api.listJobs).mockResolvedValue([]);

    let stickvPageRenderCount = 0;
    function MonitoredStickvPage() {
      const countRef = useRef(0);
      countRef.current += 1;
      stickvPageRenderCount = countRef.current;
      return <StickvPage />;
    }

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/stickv']}>
          <ToastProvider>
            <RenderJobProvider>
              <nav>
                <Link to="/library">Đi tới Thư viện</Link>
              </nav>
              <Routes>
                <Route path="/stickv" element={<MonitoredStickvPage />} />
                <Route path="/library" element={<div>Trang Thư viện</div>} />
              </Routes>
              <GlobalJobDock />
            </RenderJobProvider>
          </ToastProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByDisplayValue('Đây là beat mở đầu.')).toBeInTheDocument();

    // Mở Popover Xuất video trên Topbar rồi bấm Xuất bản đẹp (MP4)
    fireEvent.click(screen.getByRole('button', { name: 'Xuất video' }));
    const exportFinalBtn = screen.getByRole('button', { name: /Xuất bản đẹp \(MP4\)/i });
    await waitFor(() => expect(exportFinalBtn).toBeEnabled());
    fireEvent.click(exportFinalBtn);

    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    expect(FakeEventSource.instances[0].url).toBe('/api/jobs/sv-job-99/events');

    // Ghi nhận số lần render của StickvPage ngay khi job bắt đầu chạy
    const rendersBeforeProgressTicks = stickvPageRenderCount;

    // Phát liên tiếp các sự kiện tiến độ 15% -> 48% -> 82%
    act(() => {
      FakeEventSource.instances[0].emit('progress', {
        progress: 15,
        step: 'Sinh giọng VieNeu-TTS',
        stage: 'Sinh giọng VieNeu-TTS',
        current_beat: 1,
        total_beats: 4,
      });
    });
    act(() => {
      FakeEventSource.instances[0].emit('progress', {
        progress: 48,
        step: 'Dựng khung hình',
        stage: 'Dựng khung hình',
        message: 'Đang dựng cụm 2/4',
        current_beat: 2,
        total_beats: 4,
      });
    });

    // StickvPage re-render ĐÚNG 0 LẦN khi progress nhảy liên tục!
    expect(stickvPageRenderCount).toBe(rendersBeforeProgressTicks);

    // Nút Xuất trên Topbar vẫn cập nhật mượt mà qua external store: "Đang xuất · 48%"
    expect(screen.getByRole('button', { name: /Đang xuất · 48%/i })).toBeInTheDocument();
    expect(screen.getByText(/Dựng khung hình/)).toBeInTheDocument();
    expect(screen.getByText(/Beat 2\/4/)).toBeInTheDocument();

    // Khi đang ở trang /stickv, GlobalJobDock TỰ ĐỘNG ẨN để không bị 3 thanh tiến độ trùng lặp
    expect(screen.queryByRole('complementary', { name: 'Tiến trình dựng toàn cục' })).toBeNull();
    expect(screen.queryByRole('region', { name: 'Tiến trình dựng video StickV' })).toBeNull();

    // Chuyển sang trang Thư viện -> GlobalJobDock TỰ ĐỘNG HIỆN ở góc dưới phải
    fireEvent.click(screen.getByRole('link', { name: 'Đi tới Thư viện' }));
    expect(await screen.findByText('Trang Thư viện')).toBeInTheDocument();

    const dock = screen.getByRole('complementary', { name: 'Tiến trình dựng toàn cục' });
    expect(dock).toBeInTheDocument();
    const dockLink = within(dock).getByRole('link', { name: /Xem tiến trình StickV/i });
    expect(dockLink).toHaveAttribute('href', '/stickv?slug=demo-stickv');

    // Tiến độ tăng lên 74% trong lúc đang ở trang Thư viện
    act(() => {
      FakeEventSource.instances[0].emit('progress', {
        progress: 74,
        step: 'Trộn âm thanh -14 LUFS',
        stage: 'Trộn âm thanh -14 LUFS',
        message: 'Đang nén âm chuẩn -14 LUFS',
      });
    });
    expect(within(dock).getByText(/74%/)).toBeInTheDocument();

    // Bấm nút trong GlobalJobDock để quay về /stickv -> GlobalJobDock tự ẩn lại, Topbar hiện Đang xuất · 74%
    fireEvent.click(dockLink);

    expect(await screen.findByRole('button', { name: /Đang xuất · 74%/i })).toBeInTheDocument();
    expect(screen.queryByRole('complementary', { name: 'Tiến trình dựng toàn cục' })).toBeNull();
    expect(FakeEventSource.instances).toHaveLength(1);
  });
});
