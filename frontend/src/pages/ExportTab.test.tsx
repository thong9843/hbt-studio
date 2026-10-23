import { act, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { RenderOptions, RenderRecord } from '../api/types';
import { FakeEventSource, stubFetch } from '../test/fakes';
import { project } from '../test/project';
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

function open(renders: RenderRecord[] = [], extra: Record<string, unknown> = {}) {
  const started: RenderOptions[] = [];
  stubFetch({
    'GET /api/projects/muoi': project(),
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
    '/p/muoi/export',
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
    expect(screen.getByText('Xem nhanh', { selector: '.chip' })).toBeInTheDocument();
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
});
