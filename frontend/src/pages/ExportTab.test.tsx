import { act, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { RenderOptions, RenderRecord } from '../api/types';
import { FakeEventSource, stubFetch } from '../test/fakes';
import { project, scene } from '../test/project';
import { renderWithProviders } from '../test/render';
import { ComposePage } from './ComposePage';
import { ExportTab } from './ExportTab';

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal('EventSource', FakeEventSource);
});
afterEach(() => vi.unstubAllGlobals());

const record = (over: Partial<RenderRecord> = {}): RenderRecord => ({
  job_id: 'j1',
  preview: true,
  preview_seconds: null,
  fps: 30,
  duration: 20,
  created_at: '2026-10-23T10:00:00Z',
  video: '/api/files/v.mp4',
  width: 540,
  height: 960,
  lufs: -14,
  aligner: 'silence',
  music_start: null,
  music_start_source: null,
  music_matches_current: false,
  size: 1000,
  srt: null,
  publish: null,
  log: null,
  cover: null,
  youtube_cover: null,
  ...over,
});

const ready = () =>
  project({
    voice: 'voice.wav',
    scenes: [
      scene({ image: 'images/scene-01.png' }),
      scene({ image: 'images/scene-02.png' }),
      scene({ image: 'images/scene-03.png' }),
    ],
  });

function open(
  renders: RenderRecord[] = [],
  extra: Record<string, unknown> = {},
  route = '/p/muoi/export',
) {
  const started: RenderOptions[] = [];
  stubFetch({
    'GET /api/projects/muoi': ready(),
    'GET /api/health': { ok: true, ffmpeg: true, whisper: false, gpu: false, missing: [] },
    'GET /api/projects/muoi/renders': renders,
    'POST /api/projects/muoi/lint': {
      issues: [],
      counts: { info: 0, warn: 0, block: 0 },
      blocked: false,
      problems: [],
    },
    ...extra,
    'POST /api/projects/muoi/render': (_url: string, init?: RequestInit) => {
      started.push(JSON.parse(String(init?.body)) as RenderOptions);
      return new Response(JSON.stringify({ job_id: 'j1' }), {
        status: 202,
        headers: { 'Content-Type': 'application/json' },
      });
    },
  });
  renderWithProviders(
    <Routes>
      <Route path="/p/:slug" element={<ComposePage />}>
        <Route path="export" element={<ExportTab />} />
      </Route>
    </Routes>,
    route,
  );
  return started;
}

describe('Export tab: quick preview', () => {
  it('the main Xem nhanh button asks for the first 10 seconds only', async () => {
    const started = open();
    const user = userEvent.setup();
    const button = await screen.findByRole('button', { name: 'Xem nhanh' });
    await waitFor(() => expect(button).toBeEnabled());
    await user.click(button);
    await waitFor(() => expect(started).toHaveLength(1));
    expect(started[0]).toMatchObject({ preview: true, preview_seconds: 10 });
  });

  it('keeps an option to preview the whole video (no preview_seconds)', async () => {
    const started = open();
    const user = userEvent.setup();
    const button = await screen.findByRole('button', { name: 'Xem nhanh cả video' });
    await waitFor(() => expect(button).toBeEnabled());
    await user.click(button);
    await waitFor(() => expect(started).toHaveLength(1));
    expect(started[0].preview).toBe(true);
    expect(started[0]).not.toHaveProperty('preview_seconds');
  });

  it('never sends preview_seconds with the final render', async () => {
    const started = open();
    const user = userEvent.setup();
    const button = await screen.findByRole('button', { name: /Xuất bản đẹp/ });
    await waitFor(() => expect(button).toBeEnabled());
    await user.click(button);
    await waitFor(() => expect(started).toHaveLength(1));
    expect(started[0].preview).toBe(false);
    expect(started[0]).not.toHaveProperty('preview_seconds');
  });

  it('labels the history rows: 10 s head, whole-video preview, final', async () => {
    open([
      record({ job_id: 'a', preview_seconds: 10 }),
      record({ job_id: 'b' }),
      record({ job_id: 'c', preview: false, fps: 50 }),
    ]);
    expect(await screen.findByText('Xem nhanh 10 giây đầu')).toBeInTheDocument();
    expect(screen.getByText('Xem nhanh', { selector: '.ui-badge' })).toBeInTheDocument();
    expect(screen.getByText('Bản đẹp')).toBeInTheDocument();
  });

  it('shows a dash instead of the loudness when the head preview did not measure it', async () => {
    const job = {
      id: 'j1',
      project: 'muoi',
      status: 'done',
      progress: 100,
      step: 'Xong',
      log_tail: [],
      error: null,
      needs_confirmation: false,
      preview: true,
      preview_seconds: 10,
      output: {
        video: '/api/files/v.mp4',
        srt: null,
        publish: '/api/files/p.txt',
        log: '/api/files/l.txt',
        fps: 30,
        width: 540,
        height: 960,
        duration: 10,
        lufs: null,
        preview_seconds: 10,
        aligner: 'silence',
        seconds: 12,
        warnings: [],
      },
    };
    open([], { 'GET /api/jobs/j1': job, 'GET /api/files/p.txt': '' });
    const user = userEvent.setup();
    const button = await screen.findByRole('button', { name: 'Xem nhanh' });
    await waitFor(() => expect(button).toBeEnabled());
    await user.click(button);
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    act(() => FakeEventSource.instances[0].emit('end', { status: 'done' }));
    expect(await screen.findByText('Độ lớn')).toBeInTheDocument();
    expect(screen.getByText('Độ lớn').nextElementSibling).toHaveTextContent('—');
    expect(screen.queryByText('captions.srt')).not.toBeInTheDocument();
  });
  it('shows which aligner built the video, with the model, device and match ratio', async () => {
    const job = {
      id: 'j1',
      project: 'muoi',
      status: 'done',
      progress: 100,
      step: 'Xong',
      log_tail: [],
      error: null,
      needs_confirmation: false,
      preview: true,
      preview_seconds: null,
      output: {
        video: '/api/files/v.mp4',
        srt: null,
        publish: '/api/files/p.txt',
        log: '/api/files/l.txt',
        fps: 30,
        width: 540,
        height: 960,
        duration: 50,
        lufs: -14,
        preview_seconds: null,
        aligner: 'whisper',
        aligner_info: {
          model: 'small',
          device: 'cpu',
          match_ratio: 0.9712,
          skipped: ['large-v3 (cuda, int8_float16): lỗi lúc nạp model: x'],
        },
        seconds: 80,
        warnings: [],
      },
    };
    open([], { 'GET /api/jobs/j1': job, 'GET /api/files/p.txt': '' });
    const user = userEvent.setup();
    const button = await screen.findByRole('button', { name: 'Xem nhanh' });
    await waitFor(() => expect(button).toBeEnabled());
    await user.click(button);
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    act(() => FakeEventSource.instances[0].emit('end', { status: 'done' }));
    expect(await screen.findByText('Whisper small · CPU')).toBeInTheDocument();
    expect(screen.getByText('Khớp 97,1% âm tiết của kịch bản.')).toBeInTheDocument();
    expect(screen.getByText(/Đã bỏ qua: large-v3 \(cuda/)).toBeInTheDocument();
  });
  const baseJob = {
    id: 'j1',
    project: 'muoi',
    progress: 100,
    step: 'Xong',
    log_tail: [],
    preview: true,
    preview_seconds: null,
  };
  const baseOutput = {
    video: '/api/files/v.mp4',
    srt: null,
    publish: '/api/files/p.txt',
    log: '/api/files/l.txt',
    fps: 30,
    width: 540,
    height: 960,
    duration: 50,
    lufs: -14,
    preview_seconds: null,
    aligner: 'whisper',
    seconds: 80,
    warnings: [],
  };

  async function runJob(job: Record<string, unknown>, status: string) {
    open([], { 'GET /api/jobs/j1': job, 'GET /api/files/p.txt': '' });
    const user = userEvent.setup();
    const button = await screen.findByRole('button', { name: 'Xem nhanh' });
    await waitFor(() => expect(button).toBeEnabled());
    await user.click(button);
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    act(() => FakeEventSource.instances[0].emit('end', { status }));
  }

  it('lets you listen to the voice tail that was cut, next to the result', async () => {
    await runJob(
      {
        ...baseJob,
        status: 'done',
        error: null,
        needs_confirmation: false,
        output: {
          ...baseOutput,
          trimmed_tail: '/api/files/projects/muoi/renders/j1/trimmed_tail.wav',
          trimmed_tail_seconds: 3.7,
        },
      },
      'done',
    );
    expect(await screen.findByText(/Đã cắt 3,7 giây thừa ở cuối file giọng/)).toBeInTheDocument();
    expect(screen.getByLabelText('Nghe phần giọng đã cắt')).toHaveAttribute(
      'src',
      '/api/files/projects/muoi/renders/j1/trimmed_tail.wav',
    );
  });

  it('shows no player when nothing was cut', async () => {
    await runJob(
      {
        ...baseJob,
        status: 'done',
        error: null,
        needs_confirmation: false,
        output: { ...baseOutput, trimmed_tail: null, trimmed_tail_seconds: null },
      },
      'done',
    );
    expect(await screen.findByText('Căn chữ')).toBeInTheDocument();
    expect(screen.queryByLabelText('Nghe phần giọng đã cắt')).toBeNull();
  });

  it('plays the part that will be cut inside the over-8-seconds confirmation box', async () => {
    await runJob(
      {
        ...baseJob,
        status: 'failed',
        error: 'Đuôi thừa dài 9,50 giây (> 8 giây)',
        needs_confirmation: true,
        cut_audio: '/api/files/projects/muoi/renders/j1/trimmed_tail.wav',
        output: null,
      },
      'failed',
    );
    expect(await screen.findByLabelText('Nghe phần sẽ bị cắt')).toHaveAttribute(
      'src',
      '/api/files/projects/muoi/renders/j1/trimmed_tail.wav',
    );
    expect(
      screen.getByRole('button', { name: 'Tôi đã nghe, cắt và dựng tiếp' }),
    ).toBeInTheDocument();
  });

  it('still asks for confirmation when no audio file is available', async () => {
    await runJob(
      {
        ...baseJob,
        status: 'failed',
        error: 'Đuôi thừa dài 9,50 giây',
        needs_confirmation: true,
        cut_audio: null,
        output: null,
      },
      'failed',
    );
    expect(
      await screen.findByRole('button', { name: 'Tôi đã nghe, cắt và dựng tiếp' }),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText('Nghe phần sẽ bị cắt')).toBeNull();
  });
});
