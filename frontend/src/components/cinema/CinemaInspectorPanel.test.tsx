import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { StickvProject } from '../../api/types';
import { stubFetch } from '../../test/fakes';
import { renderWithProviders } from '../../test/render';
import { ToastProvider } from '../Toast';
import { CinemaInspectorPanel } from './CinemaInspectorPanel';

afterEach(() => vi.unstubAllGlobals());

const SAMPLE_STICKV: StickvProject = {
  slug: 'cinema-ui-demo',
  title: 'Kiểm thử Cinema Core UI',
  topic: 'science',
  aspect: '9:16',
  theme: 'cream',
  fps: 30,
  voice_id: 'Thanh Bình',
  music_mood: 'curious_science',
  gemini_model: 'gemini-3.8-flash',
  target_minutes: 1,
  created_at: '2026-11-19T00:00:00Z',
  updated_at: '2026-11-19T00:00:00Z',
  beats: [
    {
      id: 'b001',
      chapter: 1,
      narration: 'Tia sét nóng gấp 5 lần bề mặt Mặt Trời.',
      pose: 'present_board',
      facing: 'right',
      motion: 'bounce',
      sfx_tag: 'whoosh',
      board_type: 'big_number',
      board_title: 'Nhiệt độ tia sét',
      board_data: { items: ['**30.000°C** so với 5.500°C'], number: '30.000°C' },
      media_path: '',
      duration_sec: 3.0,
    },
  ],
};

describe('CinemaInspectorPanel', () => {
  it('displays CPU hardware badge, runs preflight auto-reflow, opens Contact Sheet, and renders cached beat', async () => {
    stubFetch({
      'GET /api/cinema/hardware': {
        mode: 'cpu',
        video_encoder: 'libx264',
        gpu_name: null,
        nvenc_probed: true,
        nvenc_probe_error: 'no gpu',
        layer_cache_mb: 256,
        ffmpeg_threads: 2,
      },
      'POST /api/cinema/preflight': {
        ok: true,
        errors: [],
        warnings: [],
        fixed_count: 2,
        repaired_spec: {
          slug: 'cinema-ui-demo',
          title: 'Kiểm thử Cinema Core UI',
          aspect: '9:16',
          fps: 30,
          preflight_passed: true,
          beats: [{ id: 'b001', shot_type: 'data_spotlight', transition_in: 'editorial_cut' }],
        },
        stats: {
          bbox_reflows: 1,
          anti_parrot_rewrites: 0,
          pacing_diversifications: 1,
          recap_conversions: 0,
        },
      },
      'POST /api/cinema/contact-sheet': {
        ok: true,
        filename: 'sheet_demo.jpg',
        url: '/api/cinema/contact-sheet/sheet_demo.jpg',
        preflight_ok: true,
        preflight_fixed: 2,
        width: 1180,
        height: 492,
        beats_rendered: 1,
        elapsed_ms: 142.5,
      },
      'POST /api/cinema/render-beat': {
        ok: true,
        beat_id: 'b001',
        cache_hit: true,
        cache_key: 'abc123_prev',
        filename: 'abc123_prev.mp4',
        url: '/api/cinema/beat-file/abc123_prev.mp4',
        elapsed_ms: 4.2,
        width: 540,
        height: 960,
      },
    });

    const user = userEvent.setup();
    renderWithProviders(
      <ToastProvider>
        <CinemaInspectorPanel stickvProject={SAMPLE_STICKV} beatId="b001" />
      </ToastProvider>,
    );

    expect(await screen.findByText('CPU kẹp 2 luồng · Cache 256 MB')).toBeVisible();

    await user.click(screen.getByRole('button', { name: 'Kiểm định & Tự nắn bố cục' }));
    expect(await screen.findByText('Đã tự nắn 2 lỗi bố cục/nội dung')).toBeVisible();
    expect(screen.getByText('Nắn hộp: 1')).toBeVisible();

    await user.click(screen.getByRole('button', { name: 'Xem Contact Sheet 1 trang' }));
    expect(await screen.findByRole('dialog')).toBeVisible();
    expect(screen.getByAltText('Contact Sheet toàn bộ kịch bản')).toHaveAttribute(
      'src',
      '/api/cinema/contact-sheet/sheet_demo.jpg',
    );
    await user.click(screen.getByRole('button', { name: 'Đóng' }));

    await user.click(screen.getByRole('button', { name: 'Xem nhanh Beat hiện tại' }));
    expect(await screen.findByText('Cache HIT (tức thì)')).toBeVisible();
  });
});
