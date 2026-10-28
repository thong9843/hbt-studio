import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { RenderOptions } from '../api/types';
import { ToastProvider } from '../components/Toast';
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

const ok = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const ready = () =>
  project({
    voice: 'voice.wav',
    scenes: [1, 2, 3].map((n) => scene({ image: `images/scene-0${n}.png` })),
  });
const lintOk = {
  issues: [],
  counts: { info: 0, warn: 0, block: 0 },
  blocked: false,
  problems: [],
};
const record = (over: Record<string, unknown>) => ({
  job_id: 'j1',
  preview: false,
  preview_seconds: null,
  fps: 50,
  duration: 50,
  render_seconds: 100,
  created_at: '2026-10-23T10:00:00Z',
  video: '/api/files/projects/muoi/renders/j1/video.mp4',
  width: 1080,
  height: 1920,
  lufs: -14,
  aligner: 'silence',
  music_start: null,
  music_start_source: null,
  music_matches_current: false,
  size: 1000,
  srt: '/api/files/projects/muoi/renders/j1/captions.srt',
  publish: null,
  log: null,
  cover: '/api/files/projects/muoi/renders/j1/cover_9x16.jpg',
  youtube_cover: null,
  ...over,
});

function Where() {
  const l = useLocation();
  return <output data-testid="where">{l.pathname}</output>;
}

function open(opts: {
  proj?: ReturnType<typeof ready>;
  lint?: unknown;
  renders?: unknown[];
  state?: unknown;
  extra?: Record<string, unknown>;
}) {
  const started: RenderOptions[] = [];
  const mock = stubFetch({
    'GET /api/projects/muoi': opts.proj ?? ready(),
    'PUT /api/projects/muoi': (_u: string, init?: RequestInit) =>
      ok(JSON.parse(String(init?.body))),
    'GET /api/health': { ok: true, ffmpeg: true, whisper: false, gpu: false, missing: [] },
    'GET /api/projects/muoi/renders': opts.renders ?? [],
    'POST /api/projects/muoi/lint': opts.lint ?? lintOk,
    'POST /api/projects/muoi/render': (_u: string, init?: RequestInit) => {
      started.push(JSON.parse(String(init?.body)) as RenderOptions);
      return ok({ job_id: 'j1' }, 202);
    },
    ...opts.extra,
  });
  renderWithProviders(
    <ToastProvider>
      <Routes>
        <Route path="/p/:slug" element={<ComposePage />}>
          <Route index element={<Where />} />
          <Route path="export" element={<ExportTab />} />
        </Route>
      </Routes>
    </ToastProvider>,
    { pathname: '/p/muoi/export', state: opts.state },
  );
  return { started, mock };
}

const settle = () => new Promise((r) => setTimeout(r, 200));

describe('Xuất video: Kiểm tra', () => {
  it('says Sẵn sàng with the three counts when nothing is wrong', async () => {
    open({});
    const card = await screen.findByRole('region', { name: 'Kiểm tra trước khi dựng' });
    expect(await within(card).findByText('Sẵn sàng')).toBeInTheDocument();
    expect(within(card).getByText('Chặn')).toBeInTheDocument();
    expect(within(card).getByText('Cảnh báo')).toBeInTheDocument();
    expect(within(card).getByText('Lưu ý')).toBeInTheDocument();
  });

  it('says Có cảnh báo, and each issue links to its scene', async () => {
    const user = userEvent.setup();
    open({
      lint: {
        issues: [
          {
            scene_index: 1,
            field: 'voice',
            category: 'x',
            level: 'warn',
            message: 'Có từ nhạy cảm',
            word: 'bia',
            hint: '',
          },
        ],
        counts: { info: 0, warn: 1, block: 0 },
        blocked: false,
        problems: [],
      },
    });
    expect(await screen.findByText('Có cảnh báo')).toBeInTheDocument();
    await user.click(screen.getByRole('link', { name: 'Đến cảnh 2' }));
    expect(await screen.findByTestId('where')).toHaveTextContent('/p/muoi');
  });

  it('says Bị chặn and turns the render buttons off', async () => {
    open({
      lint: { issues: [], counts: { info: 0, warn: 0, block: 1 }, blocked: true, problems: [] },
    });
    expect(await screen.findByText('Bị chặn')).toBeInTheDocument();
    for (const b of screen.getAllByRole('button', { name: /^Xem nhanh/ })) expect(b).toBeDisabled();
    expect(screen.getByRole('button', { name: /Xuất bản đẹp/ })).toBeDisabled();
  });

  it('lists missing materials and keeps the buttons off', async () => {
    open({ proj: project() });
    const card = await screen.findByRole('region', { name: 'Kiểm tra trước khi dựng' });
    expect(await within(card).findByText(/Thiếu ảnh cảnh 3/)).toBeInTheDocument();
    expect(within(card).getByText(/Thiếu giọng đọc/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Xuất bản đẹp/ })).toBeDisabled();
  });
});

describe('Xuất video: Xem nhanh tự dựng', () => {
  it('builds the first 10 seconds once when opened with state.auto = preview', async () => {
    const { started } = open({ state: { auto: 'preview' } });
    await waitFor(() => expect(started).toHaveLength(1));
    expect(started[0]).toMatchObject({ preview: true, preview_seconds: 10 });
    expect(FakeEventSource.instances).toHaveLength(1);
    await settle();
    expect(started).toHaveLength(1);
  });

  it('does not build without the flag (Xuất bản đẹp only switches tab)', async () => {
    const { started } = open({});
    await screen.findByText('Sẵn sàng');
    await settle();
    expect(started).toHaveLength(0);
    expect(FakeEventSource.instances).toHaveLength(0);
  });

  it('does not build when materials are missing: the check card shows why', async () => {
    const { started } = open({ proj: project(), state: { auto: 'preview' } });
    expect((await screen.findAllByText(/Thiếu giọng đọc/)).length).toBeGreaterThan(0);
    await settle();
    expect(started).toHaveLength(0);
  });

  it('does not build when the check blocks', async () => {
    const { started } = open({
      state: { auto: 'preview' },
      lint: { issues: [], counts: { info: 0, warn: 0, block: 1 }, blocked: true, problems: [] },
    });
    await screen.findByText('Bị chặn');
    await settle();
    expect(started).toHaveLength(0);
  });
});

describe('Xuất video: dựng, ước tính, huỷ', () => {
  it('shows "Đang ước tính…" at 0%, then "Còn ≈ …", and Huỷ cancels the job', async () => {
    const user = userEvent.setup();
    const { mock } = open({
      extra: { 'POST /api/jobs/j1/cancel': { id: 'j1', status: 'cancelled' } },
    });
    const fast = await screen.findByRole('button', { name: 'Xem nhanh' });
    await waitFor(() => expect(fast).toBeEnabled());
    await user.click(fast);
    const bar = await screen.findByRole('region', { name: 'Tiến độ' });
    expect(within(bar).getByText('Đang ước tính…')).toBeInTheDocument();
    act(() =>
      FakeEventSource.instances[0].emit('progress', { progress: 50, step: 'Ghép', message: '' }),
    );
    expect(within(bar).getByText(/^Còn ≈ /)).toBeInTheDocument();
    await user.click(within(bar).getByRole('button', { name: 'Huỷ dựng' }));
    expect(mock).toHaveBeenCalledWith(
      '/api/jobs/j1/cancel',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('final render uses the chosen fps chip and the outro switch', async () => {
    const user = userEvent.setup();
    const { started } = open({});
    await user.click(await screen.findByRole('button', { name: '60' }));
    await user.click(screen.getByRole('switch', { name: 'Outro' }));
    const final = screen.getByRole('button', { name: 'Xuất bản đẹp 60fps' });
    await waitFor(() => expect(final).toBeEnabled());
    await user.click(final);
    await waitFor(() => expect(started).toHaveLength(1));
    expect(started[0]).toMatchObject({ preview: false, fps: 60, outro: false });
  });

  it('shows the default estimate with no history (13.B5: 3 s per video second, 3 scenes x 6 s)', async () => {
    open({});
    await waitFor(() =>
      expect(document.querySelector('[data-slot="estimate"]')).toHaveTextContent(
        'Xem nhanh ≈ 40 giây · Bản đẹp 50 fps ≈ 54 giây',
      ),
    );
  });
});

describe('Xuất video: lịch sử dạng lưới', () => {
  it('selects a past render: player, downloads, result and the yellow ring', async () => {
    const user = userEvent.setup();
    open({
      renders: [
        record({ job_id: 'j1' }),
        record({
          job_id: 'j0',
          preview: true,
          preview_seconds: 10,
          created_at: '2026-10-22T10:00:00Z',
          video: '/api/files/projects/muoi/renders/j0/video.mp4',
          srt: null,
          cover: null,
        }),
      ],
    });
    const grid = await screen.findByRole('region', { name: 'Lịch sử các lần xuất' });
    const items = await within(grid).findAllByRole('button', { name: /^Xem / });
    expect(items).toHaveLength(2);
    expect(within(grid).getByText('Xem nhanh 10 giây đầu')).toBeInTheDocument();
    expect(within(grid).getByText('Bản đẹp')).toBeInTheDocument();

    await user.click(items[0]);
    expect(items[0]).toHaveAttribute('aria-pressed', 'true');
    expect(items[0].closest('li')).toHaveClass('ui-history-on');
    expect(screen.getByLabelText('Trình phát video đã dựng')).toHaveAttribute(
      'src',
      '/api/files/projects/muoi/renders/j1/video.mp4',
    );
    expect(screen.getByRole('link', { name: 'Tải video.mp4' })).toHaveAttribute(
      'download',
      'video.mp4',
    );
    expect(screen.getByRole('region', { name: 'Kết quả' })).toHaveTextContent('0:50');

    await user.click(items[1]);
    expect(items[0]).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByLabelText('Trình phát video đã dựng')).toHaveAttribute(
      'src',
      '/api/files/projects/muoi/renders/j0/video.mp4',
    );
  });
});

describe('Xuất video: nút tải nằm trong khung Xuất', () => {
  const j1 = '/api/files/projects/muoi/renders/j1';

  it('puts the download buttons in the same card as "Xuất bản đẹp", right below the render buttons', async () => {
    open({ renders: [record({ job_id: 'j1' })] });
    const final = await screen.findByRole('button', { name: /Xuất bản đẹp 50fps/ });
    const card = final.closest('section') as HTMLElement;
    const group = await within(card).findByRole('group', { name: 'Tải về' });
    expect(within(group).getByRole('link', { name: 'Tải video.mp4' })).toBeInTheDocument();
    // Chỉ giữ tải video: không có captions.srt, bìa 9:16, bìa YouTube.
    expect(within(group).getAllByRole('link')).toHaveLength(1);
    // Sau nút Xuất bản đẹp trong cùng khung; nút tải là nút phụ (không vàng), nút chính vẫn là vàng.
    expect(final.compareDocumentPosition(group) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    for (const a of within(group).getAllByRole('link')) {
      expect(a.tagName).toBe('A');
      expect(a).toHaveClass('ui-btn', 'ui-btn-soft');
      expect(a).not.toHaveClass('ui-btn-accent');
    }
    expect(final).toHaveClass('ui-btn-accent');
  });

  it('has no second download block under the player', async () => {
    open({ renders: [record({ job_id: 'j1' })] });
    await screen.findByLabelText('Trình phát video đã dựng');
    expect(screen.getAllByRole('link', { name: 'Tải video.mp4' })).toHaveLength(1);
    expect(screen.getAllByRole('group', { name: 'Tải về' })).toHaveLength(1);
    const player = screen.getByLabelText('Trình phát video đã dựng').closest('section')!;
    expect(within(player).queryByRole('link')).toBeNull();
  });

  it('survives a page reload: the newest render is shown with the right /files link', async () => {
    open({
      renders: [
        record({ job_id: 'j1' }),
        record({
          job_id: 'j0',
          created_at: '2026-10-22T10:00:00Z',
          video: '/api/files/projects/muoi/renders/j0/video.mp4',
        }),
      ],
    });
    const link = await screen.findByRole('link', { name: 'Tải video.mp4' });
    expect(link).toHaveAttribute('href', `${j1}/video.mp4`);
    expect(screen.getByLabelText('Trình phát video đã dựng')).toHaveAttribute(
      'src',
      `${j1}/video.mp4`,
    );
  });

  it('offers only the video download, even when srt and both covers exist', async () => {
    open({
      renders: [
        record({
          job_id: 'j1',
          youtube_cover: '/api/files/projects/muoi/renders/j1/youtube_3x2.jpg',
        }),
      ],
    });
    await screen.findByRole('link', { name: 'Tải video.mp4' });
    const group = screen.getByRole('group', { name: 'Tải về' });
    expect(within(group).getAllByRole('link')).toHaveLength(1);
    for (const name of ['Tải captions.srt', 'Tải cover_9x16.jpg', 'Tải youtube_3x2.jpg']) {
      expect(screen.queryByRole('link', { name })).toBeNull();
    }
  });

  it('shows no download group before anything was rendered', async () => {
    open({ renders: [] });
    await screen.findByRole('button', { name: /Xuất bản đẹp 50fps/ });
    expect(screen.queryByRole('group', { name: 'Tải về' })).toBeNull();
  });
});

describe('Xuất video: xoá lần xuất ở Lịch sử', () => {
  const del = (id: string) => `DELETE /api/projects/muoi/renders/${id}`;
  const r1 = () => record({ job_id: 'j1' });
  const r0 = () =>
    record({
      job_id: 'j0',
      created_at: '2026-10-22T10:00:00Z',
      video: '/api/files/projects/muoi/renders/j0/video.mp4',
      cover: null,
    });

  const cardCount = () =>
    within(screen.getByRole('region', { name: 'Lịch sử các lần xuất' })).queryAllByRole('listitem')
      .length;

  async function openMenuOf(user: ReturnType<typeof userEvent.setup>, job: string) {
    const grid = await screen.findByRole('region', { name: 'Lịch sử các lần xuất' });
    const cards = await within(grid).findAllByRole('listitem');
    const card = cards.find((li) =>
      li.querySelector(`[aria-label*="${job === 'j1' ? '23' : '22'}"]`),
    );
    const menu = within(card ?? cards[0]).getByRole('button', { name: /^Thao tác:/ });
    await user.click(menu);
  }

  it('asks first with the exact warning; Huỷ calls no API and keeps the card', async () => {
    const user = userEvent.setup();
    const { mock } = open({ renders: [r1(), r0()], extra: { [del('j1')]: () => ok({}, 204) } });
    await openMenuOf(user, 'j1');
    await user.click(screen.getByRole('menuitem', { name: 'Xoá' }));
    const dialog = await screen.findByRole('alertdialog', { name: 'Xoá lần xuất này?' });
    expect(dialog).toHaveTextContent(
      'Xoá video, bìa và publish.txt của lần xuất này. Không hoàn tác được.',
    );
    await user.click(within(dialog).getByRole('button', { name: 'Huỷ' }));
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
    expect(mock.mock.calls.some(([, init]) => (init as RequestInit)?.method === 'DELETE')).toBe(
      false,
    );
    expect(cardCount()).toBe(2);
  });

  it('confirm: releases the <video> file first, calls DELETE, the card disappears, Toast + refresh', async () => {
    const user = userEvent.setup();
    let list = [r1(), r0()];
    let videoSrcAtDelete: string | null | undefined;
    const { mock } = open({
      renders: list,
      extra: {
        'GET /api/projects/muoi/renders': () => ok(list),
        [del('j1')]: () => {
          videoSrcAtDelete = document.querySelector('video')?.getAttribute('src');
          list = list.filter((r) => r.job_id !== 'j1');
          return new Response(null, { status: 204 });
        },
      },
    });
    await screen.findByLabelText('Trình phát video đã dựng'); // j1 (mới nhất) đang phát
    await openMenuOf(user, 'j1');
    await user.click(screen.getByRole('menuitem', { name: 'Xoá' }));
    const dialog = await screen.findByRole('alertdialog');
    await user.click(within(dialog).getByRole('button', { name: 'Xoá' }));

    expect(await screen.findByText('Đã xoá lần xuất')).toBeInTheDocument();
    expect(videoSrcAtDelete).toBeNull(); // src đã gỡ trước khi gọi API
    await waitFor(() => expect(cardCount()).toBe(1));
    const calls = mock.mock.calls.filter(([, init]) => (init as RequestInit)?.method === 'DELETE');
    expect(calls).toHaveLength(1);
    expect(String(calls[0][0])).toBe('/api/projects/muoi/renders/j1');
    // Lịch sử và thẻ Dự án được làm mới; trình phát chuyển sang lần xuất còn lại.
    await waitFor(() =>
      expect(screen.getByLabelText('Trình phát video đã dựng')).toHaveAttribute(
        'src',
        '/api/files/projects/muoi/renders/j0/video.mp4',
      ),
    );
  });

  it('409 shows a Toast with the reason, keeps the card and gives the video back', async () => {
    const user = userEvent.setup();
    open({
      renders: [r1(), r0()],
      extra: {
        [del('j1')]: () => ok({ detail: 'Không xoá được vì file đang mở (đóng trình phát…)' }, 409),
      },
    });
    await screen.findByLabelText('Trình phát video đã dựng');
    await openMenuOf(user, 'j1');
    await user.click(screen.getByRole('menuitem', { name: 'Xoá' }));
    const dialog = await screen.findByRole('alertdialog');
    await user.click(within(dialog).getByRole('button', { name: 'Xoá' }));
    expect(await screen.findByText(/file đang mở/)).toBeInTheDocument();
    expect(cardCount()).toBe(2);
    await waitFor(() =>
      expect(screen.getByLabelText('Trình phát video đã dựng')).toHaveAttribute(
        'src',
        '/api/files/projects/muoi/renders/j1/video.mp4',
      ),
    );
  });

  it('turns Xoá off on the card of the running job', async () => {
    const user = userEvent.setup();
    open({ renders: [r1(), r0()] });
    const final = await screen.findByRole('button', { name: /Xuất bản đẹp 50fps/ });
    await waitFor(() => expect(final).toBeEnabled());
    await user.click(final); // job mới có id "j1" (khớp thẻ j1)
    await waitFor(() => expect(FakeEventSource.instances.length).toBe(1));
    await openMenuOf(user, 'j1');
    const item = screen.getByRole('menuitem', { name: 'Xoá' });
    expect(item).toBeDisabled();
    expect(item).toHaveAttribute('title', 'Đang dựng');
  });

  it('menu also offers "Tải video" with the right file', async () => {
    const user = userEvent.setup();
    const clicked: { href: string; download: string }[] = [];
    const spy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      clicked.push({ href: this.getAttribute('href') ?? '', download: this.download });
    });
    open({ renders: [r1(), r0()] });
    await openMenuOf(user, 'j0');
    await user.click(screen.getByRole('menuitem', { name: 'Tải video' }));
    expect(clicked).toEqual([
      { href: '/api/files/projects/muoi/renders/j0/video.mp4', download: 'video.mp4' },
    ]);
    spy.mockRestore();
  });
});
