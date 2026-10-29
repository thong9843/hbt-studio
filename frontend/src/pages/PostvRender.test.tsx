import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider } from '../components/Toast';
import { FakeEventSource, json, stubFetch } from '../test/fakes';
import { renderWithProviders } from '../test/render';
import { PostvExportPage } from './PostvExportPage';
import { PostvLayout } from './PostvLayout';
import { PostvPreviewPage } from './PostvPreviewPage';

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal('EventSource', FakeEventSource);
});
afterEach(() => vi.unstubAllGlobals());

const stats = { views: null, likes: null, replies: null, reposts: null, shares: null };
const CLIP = {
  id: 'a',
  file: 'a.mp4',
  title: 'Clip a',
  source: 'Tự quay',
  license: 'Tự quay',
  url: '',
  width: 1080,
  height: 1920,
  fps: 60,
  duration: 30,
  tags: [],
};

const postv = (over: Record<string, unknown> = {}) => ({
  version: 1,
  kind: 'postv',
  slug: 'bai',
  title: 'Bài đêm khuya',
  series: '',
  source: { url: '', note: '', pasted_at: null },
  post: {
    handle: 'tac_gia',
    age: '17 giờ',
    text: 'Hôm qua mình quên ví.',
    card_text: null,
    ...stats,
  },
  comments: [],
  segments: [{ role: 'post', card: 'post', voice: 'Hôm qua mình quên ví.', ref: null }],
  hook: { text: '', accent: '' },
  background: { mode: 'auto', clip_ids: [], seed: 1, start_offset: null },
  voice: { engine: 'file', voice_id: null, file: 'voice.wav', trim_end: null, cast: {}, seed: 1 },
  music: null,
  settings: { fps: 60, captions: true, aligner: 'auto', outro: true, card_animation: 'smooth' },
  ...over,
});

const OUTPUT = {
  video: '/files/bai/renders/j1/video.mp4',
  publish: '/files/bai/renders/j1/publish.txt',
  srt: null,
  cover: null,
  youtube_cover: null,
  log: '/files/bai/renders/j1/log.txt',
  fps: 60,
  width: 1080,
  height: 1920,
  duration: 12.5,
  lufs: -14,
  preview_seconds: null,
  aligner: 'whisper',
  seconds: 31.2,
  warnings: ['Whisper rơi về khoảng lặng'],
};

const job = (status: string, over: Record<string, unknown> = {}) => ({
  id: 'j1',
  project: 'bai',
  status,
  progress: 50,
  step: 'Ghép cuối',
  log_tail: [],
  output: null,
  error: null,
  needs_confirmation: false,
  preview: false,
  preview_seconds: null,
  ...over,
});

function backend(project: unknown, extra: Record<string, unknown> = {}) {
  const renders: Record<string, unknown>[] = [];
  const saves: Record<string, unknown>[] = [];
  stubFetch({
    'GET /api/projects/bai': project,
    'PUT /api/projects/bai': (_u: string, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body));
      saves.push(body);
      return json(body);
    },
    'GET /api/backgrounds': [CLIP],
    'GET /api/jobs': [],
    'POST /api/projects/bai/render': (_u: string, init?: RequestInit) => {
      renders.push(JSON.parse(String(init?.body)));
      return json({ job_id: 'j1' }, 202);
    },
    'GET /api/projects/bai/postv/card.png': () => new Response(new Blob(['x']), { status: 200 }),
    ...extra,
  });
  return { renders, saves };
}

function app(route: string) {
  return renderWithProviders(
    <ToastProvider>
      <Routes>
        <Route path="/postv/:slug" element={<PostvLayout />}>
          <Route path="preview" element={<PostvPreviewPage />} />
          <Route path="export" element={<PostvExportPage />} />
        </Route>
      </Routes>
    </ToastProvider>,
    route,
  );
}

describe('Bước 4 · Xem nhanh', () => {
  it('starts a 10 second preview, shows progress and the finished video', async () => {
    const user = userEvent.setup();
    const { renders } = backend(postv(), {
      'GET /api/jobs/j1': job('done', {
        progress: 100,
        step: 'Xong',
        output: { ...OUTPUT, preview_seconds: 10 },
        preview: true,
        preview_seconds: 10,
      }),
    });
    app('/postv/bai/preview');
    await user.click(await screen.findByRole('button', { name: 'Xem nhanh' }));
    await waitFor(() => expect(renders).toEqual([{ preview: true, preview_seconds: 10 }]));
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    FakeEventSource.instances[0].emit('progress', { progress: 42, step: 'Căn chữ', message: '' });
    const bar = await screen.findByRole('progressbar', { name: 'Tiến độ dựng' });
    expect(bar).toHaveAttribute('aria-valuenow', '42');
    expect(screen.getByText(/Căn chữ/)).toBeVisible();
    FakeEventSource.instances[0].emit('end', { status: 'done' });
    const player = await screen.findByLabelText('Video vừa dựng');
    expect(player).toHaveAttribute('src', '/files/bai/renders/j1/video.mp4');
    expect(screen.getByText('12,5 giây · 60 fps · dựng trong 31 giây')).toBeVisible();
    expect(screen.getByText('Whisper rơi về khoảng lặng')).toBeVisible();
    expect(screen.getByRole('link', { name: 'Tải video.mp4' })).toHaveAttribute('download');
  });

  it('is disabled with the reason while the voice file is missing', async () => {
    backend(postv({ voice: { engine: 'vieneu', file: null } }));
    app('/postv/bai/preview');
    const button = await screen.findByRole('button', { name: /^Xem nhanh/ });
    expect(button).toBeDisabled();
    expect(
      screen.getByText('Chưa đủ để xem nhanh: cần lời đọc, file giọng và ít nhất một clip nền.'),
    ).toBeVisible();
  });

  it('shows the server error when the render is refused', async () => {
    const user = userEvent.setup();
    backend(postv(), {
      'POST /api/projects/bai/render': () =>
        json({ detail: 'Project chưa đủ để dựng: Chưa có clip nền nào trong thư viện' }, 422),
    });
    app('/postv/bai/preview');
    await user.click(await screen.findByRole('button', { name: 'Xem nhanh' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Chưa có clip nền nào');
  });
});

describe('Bước 5 · Xuất bản đẹp', () => {
  it('saves the fps and outro choice and renders the full video', async () => {
    const user = userEvent.setup();
    const { renders, saves } = backend(postv());
    app('/postv/bai/export');
    await user.click(await screen.findByRole('button', { name: '50 fps' }));
    await user.click(screen.getByRole('switch', { name: 'Thêm outro (4 giây)' }));
    await user.click(screen.getByRole('button', { name: 'Xuất bản đẹp 50fps' }));
    await waitFor(() => expect(renders).toEqual([{ preview: false, fps: 50, outro: false }]));
    const last = saves[saves.length - 1] as { settings: { fps: number; outro: boolean } };
    expect(last.settings.fps).toBe(50);
    expect(last.settings.outro).toBe(false);
  });

  it('cancels a running render', async () => {
    const user = userEvent.setup();
    const cancelled: string[] = [];
    backend(postv(), {
      'POST /api/jobs/j1/cancel': () => {
        cancelled.push('j1');
        return json(job('cancelled'));
      },
      'GET /api/jobs/j1': job('cancelled'),
    });
    app('/postv/bai/export');
    await user.click(await screen.findByRole('button', { name: 'Xuất bản đẹp 60fps' }));
    await user.click(await screen.findByRole('button', { name: 'Huỷ dựng' }));
    await waitFor(() => expect(cancelled).toEqual(['j1']));
    FakeEventSource.instances[0].emit('end', { status: 'cancelled' });
    expect(await screen.findByText('Đã huỷ.')).toBeVisible();
  });

  it('shows the failure reason of a failed job', async () => {
    const user = userEvent.setup();
    backend(postv(), { 'GET /api/jobs/j1': job('failed', { error: 'Bộ mã hoá lỗi' }) });
    app('/postv/bai/export');
    await user.click(await screen.findByRole('button', { name: 'Xuất bản đẹp 60fps' }));
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    FakeEventSource.instances[0].emit('end', { status: 'failed' });
    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText(/Dựng không thành công: Bộ mã hoá lỗi/)).toBeVisible();
  });

  it('blocks the export until the project is complete', async () => {
    backend(postv({ segments: [] }));
    app('/postv/bai/export');
    expect(await screen.findByRole('button', { name: /Xuất bản đẹp 60fps/ })).toBeDisabled();
  });
});
