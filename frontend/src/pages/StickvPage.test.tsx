import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api/endpoints';
import { stickvApi } from '../api/stickv';
import { GlobalJobDock } from '../components/layout/GlobalJobDock';
import { RenderJobProvider } from '../components/RenderJobProvider';
import { ToastProvider } from '../components/Toast';
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
  FakeEventSource.instances = [];
  vi.stubGlobal('EventSource', FakeEventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('StickvPage', () => {
  it('renders StickV workspace, Gemini model selector, and 9:16 / 16:9 toggle', async () => {
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

    expect(await screen.findByText(/Xưởng Video Người Que/i)).toBeInTheDocument();
    expect(await screen.findByDisplayValue('Đây là beat mở đầu.')).toBeInTheDocument();

    const modelSelect = screen.getByRole('combobox', { name: 'Chọn model Gemini' });
    expect(modelSelect).toHaveAttribute('data-value', 'gemini-3.1-flash-lite');
    fireEvent.click(modelSelect);
    expect(
      screen.getByRole('option', { name: 'Gemini 3.1 Flash Lite (Mặc định / 500 RPD)' }),
    ).toBeInTheDocument();
    fireEvent.keyDown(modelSelect, { key: 'Escape' });

    const poseSelect = screen.getByRole('combobox', { name: 'Dáng người que' });
    fireEvent.click(poseSelect);
    expect(screen.getByRole('option', { name: 'Dáng: Flow Hero' })).toBeInTheDocument();
    fireEvent.keyDown(poseSelect, { key: 'Escape' });

    const voiceSelect = await screen.findByRole('combobox', { name: 'Chọn giọng đọc VieNeu' });
    expect(voiceSelect).toHaveAttribute('data-value', 'Thanh Bình');

    fireEvent.click(screen.getByRole('tab', { name: 'Dán JSON (0 Token)' }));
    expect(screen.getByRole('button', { name: /Copy Prompt Đạo diễn/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'Dán Lời thoại' }));
    expect(screen.getByRole('button', { name: /Tách lời thoại thành Beat/i })).toBeInTheDocument();

    const toggle169 = screen.getByRole('button', { name: '16:9 Ngang' });
    fireEvent.click(toggle169);
    expect(screen.getByRole('button', { name: /1920×1080/i })).toBeInTheDocument();

    expect(screen.getByRole('combobox', { name: 'Bối cảnh sân khấu' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Chế độ diễn hoạt' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Tâm trạng nhạc' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Tương tác sân khấu' })).toBeInTheDocument();
  });

  it('persists live StickV SSE progress across route unmount/remount and shows GlobalJobDock link', async () => {
    vi.mocked(stickvApi.save).mockResolvedValue({ project: {} as never });
    vi.mocked(stickvApi.render).mockResolvedValue({
      job_id: 'sv-job-99',
      slug: 'demo-stickv',
      preview: false,
    });
    vi.mocked(api.listJobs).mockResolvedValue([]);

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
                <Route path="/stickv" element={<StickvPage />} />
                <Route path="/library" element={<div>Trang Thư viện</div>} />
              </Routes>
              <GlobalJobDock />
            </RenderJobProvider>
          </ToastProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const exportBtn = await screen.findByRole('button', { name: /Xuất bản đẹp/i });
    fireEvent.click(exportBtn);

    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    expect(FakeEventSource.instances[0].url).toBe('/api/jobs/sv-job-99/events');

    // Phát sự kiện tiến độ 48%
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

    expect(await screen.findByLabelText('Tiến trình dựng video StickV')).toBeInTheDocument();
    expect(screen.getAllByText(/48%/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Dựng khung hình/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Beat 2\/4/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole('button', { name: /Xuất bản đẹp/i })).toBeDisabled();

    // Chuyển sang trang khác (unmount StickvPage hoàn toàn)
    fireEvent.click(screen.getByRole('link', { name: 'Đi tới Thư viện' }));
    expect(await screen.findByText('Trang Thư viện')).toBeInTheDocument();
    expect(screen.queryByLabelText('Tiến trình dựng video StickV')).not.toBeInTheDocument();

    // GlobalJobDock vẫn bám sống tiến độ + có nút nhảy về đúng dự án StickV
    const dockLink = screen.getByRole('link', { name: /Xem tiến trình StickV/i });
    expect(dockLink).toHaveAttribute('href', '/stickv?slug=demo-stickv');

    // Tiến độ tăng lên 74% trong lúc đang ở trang khác
    act(() => {
      FakeEventSource.instances[0].emit('progress', {
        progress: 74,
        step: 'Trộn âm thanh -14 LUFS',
        stage: 'Trộn âm thanh -14 LUFS',
        message: 'Đang nén âm chuẩn -14 LUFS',
      });
    });
    expect(screen.getByText(/74%/)).toBeInTheDocument();

    // Bấm nút trong GlobalJobDock để quay về /stickv (remount StickvPage)
    fireEvent.click(dockLink);

    expect(await screen.findByLabelText('Tiến trình dựng video StickV')).toBeInTheDocument();
    expect(screen.getAllByText(/74%/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Trộn âm thanh -14 LUFS/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole('button', { name: /Xuất bản đẹp/i })).toBeDisabled();
    // Không tạo thêm EventSource trùng lặp khi remount
    expect(FakeEventSource.instances).toHaveLength(1);
  });
});
