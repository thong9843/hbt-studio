import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { RenderJobProvider } from '../components/RenderJobProvider';
import { ToastProvider } from '../components/Toast';
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
    },
  };
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

    const modelSelect = screen.getByLabelText('Chọn model Gemini') as HTMLSelectElement;
    expect(modelSelect.value).toBe('gemini-3.1-flash-lite');
    expect(
      screen.getByRole('option', { name: 'Gemini 3.1 Flash Lite (Mặc định / 500 RPD)' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Dáng: Flow Hero' })).toBeInTheDocument();

    const voiceSelect = (await screen.findByLabelText(
      'Chọn giọng đọc VieNeu',
    )) as HTMLSelectElement;
    expect(voiceSelect.value).toBe('Thanh Bình');

    fireEvent.click(screen.getByRole('tab', { name: 'Dán JSON (0 Token)' }));
    expect(screen.getByRole('button', { name: /Copy Prompt Đạo diễn/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'Dán Lời thoại' }));
    expect(screen.getByRole('button', { name: /Tách lời thoại thành Beat/i })).toBeInTheDocument();

    const toggle169 = screen.getByRole('button', { name: '16:9 Ngang' });
    fireEvent.click(toggle169);
    expect(screen.getByRole('button', { name: /1920×1080/i })).toBeInTheDocument();

    expect(screen.getByLabelText('Bối cảnh sân khấu')).toBeInTheDocument();
    expect(screen.getByLabelText('Chế độ diễn hoạt')).toBeInTheDocument();
    expect(screen.getByLabelText('Tâm trạng nhạc')).toBeInTheDocument();
    expect(screen.getByLabelText('Tương tác sân khấu')).toBeInTheDocument();
  });
});
