import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Project, RenderRecord, Thumbnail } from '../api/types';
import { ToastProvider } from '../components/Toast';
import { stubFetch } from '../test/fakes';
import { project } from '../test/project';
import { renderWithProviders } from '../test/render';
import { ComposePage } from './ComposePage';
import { ExportTab } from './ExportTab';

afterEach(() => vi.unstubAllGlobals());

const thumb = (over: Partial<Thumbnail> = {}): Thumbnail => ({
  scene: 1,
  lines: ['bạn có phải', 'người được', 'muỗi yêu?'],
  series: '',
  accent: '#FFD43B',
  ...over,
});

const record = (over: Partial<RenderRecord> = {}): RenderRecord => ({
  job_id: 'j1',
  preview: false,
  preview_seconds: null,
  fps: 50,
  duration: 50,
  created_at: '2026-10-23T10:00:00Z',
  video: '/api/files/v.mp4',
  width: 1080,
  height: 1920,
  lufs: -13.8,
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

const jsonResponse = (body: unknown) =>
  new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } });

function open(
  opts: {
    thumbnail?: Thumbnail | null;
    renders?: RenderRecord[];
    extra?: Record<string, unknown>;
  } = {},
) {
  const saved: Project[] = [];
  const previews: { thumbnail: Thumbnail }[] = [];
  const cleans: string[] = [];
  stubFetch({
    'GET /api/projects/muoi': project({ thumbnail: opts.thumbnail ?? null }),
    'PUT /api/projects/muoi': (_url: string, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body)) as Project;
      saved.push(body);
      return jsonResponse(body);
    },
    'GET /api/health': { ok: true, ffmpeg: true, whisper: false, gpu: false, missing: [] },
    'GET /api/projects/muoi/renders': opts.renders ?? [],
    'POST /api/projects/muoi/lint': {
      issues: [],
      counts: { info: 0, warn: 0, block: 0 },
      blocked: false,
      problems: [],
    },
    'POST /api/projects/muoi/thumbnail/preview.jpg': (_url: string, init?: RequestInit) => {
      previews.push(JSON.parse(String(init?.body)) as { thumbnail: Thumbnail });
      return new Response(new Blob(['jpg'], { type: 'image/jpeg' }), { status: 200 });
    },
    'POST /api/projects/muoi/build/clean': () => {
      cleans.push('clean');
      return jsonResponse({
        before_bytes: 3 * 1024 * 1024,
        after_bytes: 1024 * 1024,
        freed_bytes: 2 * 1024 * 1024,
        kept: ['timing.json', 'timing.json.key'],
        failed: 0,
      });
    },
    ...opts.extra,
  });
  renderWithProviders(
    <ToastProvider>
      <Routes>
        <Route path="/p/:slug" element={<ComposePage />}>
          <Route path="export" element={<ExportTab />} />
        </Route>
      </Routes>
    </ToastProvider>,
    '/p/muoi/export',
  );
  return { saved, previews, cleans };
}

describe('Export tab: cover', () => {
  it('adds an empty cover block and saves it', async () => {
    const { saved } = open();
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Thêm ảnh bìa' }));
    await waitFor(() => expect(saved).toHaveLength(1), { timeout: 3000 });
    expect(saved[0].thumbnail).toEqual({
      scene: 1,
      lines: ['', ''],
      series: '',
      accent: '#FFD43B',
    });
  });

  it('previews the draft with both crops once there are two lines', async () => {
    const { previews } = open({ thumbnail: thumb({ series: 'Vì sao vậy ta?' }) });
    expect(await screen.findByAltText('Khung 3:4 (lưới hồ sơ TikTok)')).toBeInTheDocument();
    expect(screen.getByAltText('Khung 3:2 (YouTube Shorts)')).toBeInTheDocument();
    expect(previews).toHaveLength(1);
    expect(previews[0].thumbnail.lines).toEqual(['bạn có phải', 'người được', 'muỗi yêu?']);
    expect(previews[0].thumbnail.series).toBe('Vì sao vậy ta?');
  });

  it('does not ask for a preview with fewer than two lines', async () => {
    const { previews } = open({ thumbnail: thumb({ lines: ['một', ''] }) });
    expect(await screen.findByText('Cần nhập ít nhất 2 dòng để xem trước.')).toBeInTheDocument();
    await new Promise((r) => setTimeout(r, 900));
    expect(previews).toHaveLength(0);
  });

  it('drops the optional third line when it is cleared', async () => {
    const { saved } = open({ thumbnail: thumb() });
    const user = userEvent.setup();
    const third = await screen.findByLabelText('Dòng 3 (tuỳ chọn)');
    await user.clear(third);
    await waitFor(() => expect(saved.length).toBeGreaterThan(0), { timeout: 3000 });
    expect(saved.at(-1)?.thumbnail?.lines).toEqual(['bạn có phải', 'người được']);
  });

  it('offers both files from the latest render that has them', async () => {
    open({
      thumbnail: thumb(),
      renders: [
        record({ job_id: 'new' }),
        record({
          job_id: 'old',
          cover: '/api/files/c.jpg',
          youtube_cover: '/api/files/y.jpg',
        }),
      ],
    });
    const cover = await screen.findAllByRole('link', { name: /cover_9x16\.jpg/ });
    expect(cover.some((a) => a.getAttribute('href') === '/api/files/c.jpg')).toBe(true);
    const youtube = screen.getAllByRole('link', { name: /youtube_3x2\.jpg/ });
    expect(youtube.some((a) => a.getAttribute('href') === '/api/files/y.jpg')).toBe(true);
    expect(screen.queryByText(/Chưa có file ảnh bìa/)).not.toBeInTheDocument();
  });

  it('removes the cover block', async () => {
    const { saved } = open({ thumbnail: thumb() });
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Bỏ ảnh bìa' }));
    await waitFor(() => expect(saved.length).toBeGreaterThan(0), { timeout: 3000 });
    expect(saved.at(-1)?.thumbnail).toBeNull();
  });
});

describe('Export tab: clean build files', () => {
  it('asks first, and cancelling does nothing', async () => {
    const { cleans } = open();
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Dọn file tạm' }));
    expect(await screen.findByRole('alertdialog')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Huỷ' }));
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(cleans).toHaveLength(0);
  });

  it('cleans after confirmation and reports the freed size', async () => {
    const { cleans } = open();
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Dọn file tạm' }));
    await user.click(
      within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Dọn' }),
    );
    await waitFor(() => expect(cleans).toHaveLength(1));
    expect(await screen.findByText('Đã giải phóng 2.0 MB')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
  });

  it('shows the server refusal when the project is rendering (409)', async () => {
    open({
      extra: {
        'POST /api/projects/muoi/build/clean': () =>
          new Response(JSON.stringify({ detail: 'Project đang được dựng, hãy đợi xong' }), {
            status: 409,
            headers: { 'Content-Type': 'application/json' },
          }),
      },
    });
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Dọn file tạm' }));
    await user.click(
      within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Dọn' }),
    );
    expect((await screen.findAllByText(/Project đang được dựng/)).length).toBeGreaterThan(0);
  });
});
