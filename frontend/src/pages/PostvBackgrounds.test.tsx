import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { NewProjectProvider } from '../components/NewProjectDialog';
import { ToastProvider } from '../components/Toast';
import { stubFetch } from '../test/fakes';
import { renderWithProviders } from '../test/render';
import { PostvLayout } from './PostvLayout';
import { PostvPickPage } from './PostvPickPage';
import { PostvPreviewPage } from './PostvPreviewPage';
import { PostvSourcePage } from './PostvSourcePage';
import { ProjectsPage } from './ProjectsPage';

afterEach(() => vi.unstubAllGlobals());

const clip = (id: string, over: Record<string, unknown> = {}) => ({
  id,
  file: `${id}.mp4`,
  title: `Clip ${id}`,
  source: 'Tự quay',
  license: 'Tự quay',
  url: '',
  width: 1080,
  height: 1920,
  fps: 60,
  duration: 15,
  tags: [],
  ...over,
});
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const stats = { views: null, likes: null, replies: null, reposts: null, shares: null };
const postv = (over: Record<string, unknown> = {}) => ({
  version: 1,
  kind: 'postv',
  slug: 'bai',
  title: 'Bài đêm khuya',
  series: '',
  source: { url: '', note: '', pasted_at: null },
  voice: { engine: 'vieneu', voice_id: null, file: null, trim_end: null, cast: {}, seed: 1 },
  post: {
    handle: 'tac_gia',
    age: '17 giờ',
    text: 'Hôm qua mình quên ví.',
    card_text: null,
    ...stats,
  },
  comments: [
    {
      id: 'c1',
      handle: 'user_b',
      age: '14 giờ',
      text: 'Hay',
      parent: null,
      picked: true,
      ...stats,
    },
    {
      id: 'c2',
      handle: 'user_c',
      age: '13 giờ',
      text: 'Ổn',
      parent: null,
      picked: false,
      ...stats,
    },
  ],
  segments: [{ role: 'post', card: 'post', voice: 'a'.repeat(330), ref: null }], // ≈ 20 s
  hook: { text: '', accent: '' },
  background: { mode: 'auto', clip_ids: [], seed: 1, start_offset: null },
  settings: { fps: 60, card_animation: 'smooth' },
  ...over,
});

function backend(project: unknown, clips: unknown[], extra: Record<string, unknown> = {}) {
  const saves: Record<string, unknown>[] = [];
  stubFetch({
    'GET /api/projects/bai': project,
    'PUT /api/projects/bai': (_url: string, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body));
      saves.push(body);
      return json(body);
    },
    'POST /api/projects/bai/postv/script/check': {
      seconds: 0,
      chars: 0,
      long: false,
      censored: 0,
      segments: [],
      issues: [],
    },
    'GET /api/backgrounds': clips,
    ...extra,
  });
  return saves;
}

function app(path: string) {
  return renderWithProviders(
    <ToastProvider>
      <NewProjectProvider>
        <Routes>
          <Route path="/postv" element={<ProjectsPage kind="postv" />} />
          <Route path="/postv/:slug" element={<PostvLayout />}>
            <Route index element={<PostvSourcePage />} />
            <Route path="pick" element={<PostvPickPage />} />
            <Route path="preview" element={<PostvPreviewPage />} />
          </Route>
        </Routes>
      </NewProjectProvider>
    </ToastProvider>,
    path,
  );
}

const summaries = [
  {
    slug: 'bai',
    title: 'Bài PostV',
    kind: 'postv',
    updated_at: '2026-10-29T10:00:00',
    thumb: null,
    cover: null,
    last_render: null,
    last_final: null,
    error: null,
  },
];

describe('Thư viện nền trên trang /postv', () => {
  it('says so when the library is empty and offers "Thêm clip"', async () => {
    stubFetch({ 'GET /api/projects': summaries, 'GET /api/backgrounds': [] });
    app('/postv');
    const lib = await screen.findByRole('region', { name: 'Thư viện nền' });
    expect(await within(lib).findByText(/Chưa có clip nào/)).toBeVisible();
    expect(within(lib).getByRole('button', { name: 'Thêm clip' })).toBeVisible();
  });

  it('lists clips with duration, size, licence and a low-resolution reminder', async () => {
    stubFetch({
      'GET /api/projects': summaries,
      'GET /api/backgrounds': [
        clip('a'),
        clip('b', { width: 720, height: 1280, fps: 30, duration: 7.5, license: 'CC0' }),
      ],
    });
    app('/postv');
    const lib = await screen.findByRole('region', { name: 'Thư viện nền' });
    expect(await within(lib).findByText('Clip a')).toBeVisible();
    const tiles = within(lib).getAllByRole('listitem');
    expect(within(tiles[0]).getByText(/15 s · 1080×1920 · 60 fps/)).toBeVisible();
    expect(within(tiles[0]).getByText('Giấy phép: Tự quay')).toBeVisible();
    expect(within(tiles[0]).queryByText('Dưới 1080×1920')).toBeNull();
    expect(within(tiles[1]).getByText(/7,5 s · 720×1280 · 30 fps/)).toBeVisible();
    expect(within(tiles[1]).getByText('Giấy phép: CC0')).toBeVisible();
    expect(within(tiles[1]).getByText('Dưới 1080×1920')).toBeVisible();
    expect(tiles[0].querySelector('img')).toHaveAttribute('src', '/api/backgrounds/a/thumb');
  });

  it('adds a clip: needs file + name, uploads multipart, then refreshes', async () => {
    const user = userEvent.setup();
    let list: unknown[] = [];
    const posted: FormData[] = [];
    stubFetch({
      'GET /api/projects': summaries,
      'GET /api/backgrounds': () => json(list),
      'POST /api/backgrounds': (_url: string, init?: RequestInit) => {
        posted.push(init?.body as FormData);
        list = [clip('parkour-01', { title: 'Parkour 01' })];
        return json(list[0], 201);
      },
    });
    app('/postv');
    await user.click(await screen.findByRole('button', { name: 'Thêm clip' }));
    const dialog = await screen.findByRole('dialog', { name: 'Thêm clip nền' });
    const submit = within(dialog).getByRole('button', { name: 'Thêm' });
    expect(submit).toBeDisabled();
    const file = new File(['video'], 'parkour-01.mp4', { type: 'video/mp4' });
    await user.upload(within(dialog).getByLabelText('Chọn video'), file);
    expect(within(dialog).getByText('parkour-01.mp4')).toBeVisible();
    expect(within(dialog).getByLabelText(/^Tên clip/)).toHaveValue('parkour-01'); // gợi ý từ tên file
    expect(submit).toBeEnabled();
    await user.click(submit);
    await waitFor(() => expect(posted).toHaveLength(1));
    const form = posted[0];
    expect(form.get('file')).toBeInstanceOf(File);
    expect(form.get('title')).toBe('parkour-01');
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(await screen.findByText('Parkour 01')).toBeVisible();
  });

  it('keeps the dialog open and shows the server reason when the clip is refused', async () => {
    const user = userEvent.setup();
    stubFetch({
      'GET /api/projects': summaries,
      'GET /api/backgrounds': [],
      'POST /api/backgrounds': () =>
        json({ detail: 'Chỉ nhận video dọc (cao hơn rộng); file này là 1280×720' }, 400),
    });
    app('/postv');
    await user.click(await screen.findByRole('button', { name: 'Thêm clip' }));
    const dialog = await screen.findByRole('dialog', { name: 'Thêm clip nền' });
    await user.upload(
      within(dialog).getByLabelText('Chọn video'),
      new File(['v'], 'ngang.mp4', { type: 'video/mp4' }),
    );
    await user.click(within(dialog).getByRole('button', { name: 'Thêm' }));
    expect(await within(dialog).findByText(/Chỉ nhận video dọc/)).toBeVisible();
    expect(screen.getByRole('dialog', { name: 'Thêm clip nền' })).toBeVisible();
  });
});

describe('Bước 4 · Xem trước: nền, thẻ, hiệu ứng', () => {
  it('is reachable from the stage bar', async () => {
    const user = userEvent.setup();
    backend(postv(), [clip('a')]);
    app('/postv/bai');
    await user.click(await screen.findByRole('link', { name: 'Bước 4/5: Xem trước' }));
    expect(await screen.findByRole('region', { name: 'Nền gameplay' })).toBeVisible();
  });

  it('auto mode counts every library clip against the estimated duration', async () => {
    backend(postv(), [clip('a'), clip('b'), clip('c', { duration: 7.5 })]);
    app('/postv/bai/preview');
    expect(
      await screen.findByText('3 clip, tổng 38 s · Đủ 20 s, nối bằng cắt thẳng'),
    ).toBeVisible();
    expect(screen.getByRole('button', { name: 'Tự chọn' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.queryByRole('checkbox')).toBeNull(); // chỉ chọn tay mới có ô chọn
  });

  it('manual mode: pick clips, see whether they are enough, and save the choice', async () => {
    const user = userEvent.setup();
    const saves = backend(postv(), [clip('a', { duration: 7.5 }), clip('b'), clip('c')]);
    app('/postv/bai/preview');
    await user.click(await screen.findByRole('button', { name: 'Chọn tay' }));
    expect(await screen.findByText('Chọn ít nhất một clip, hoặc để Tự chọn.')).toBeVisible();
    await user.click(screen.getByRole('checkbox', { name: 'Chọn clip Clip a' }));
    expect(screen.getByText('1 clip, tổng 8 s · Chưa đủ 20 s: chọn thêm clip')).toBeVisible();
    await user.click(screen.getByRole('checkbox', { name: 'Chọn clip Clip b' }));
    expect(screen.getByText('2 clip, tổng 23 s · Đủ 20 s, nối bằng cắt thẳng')).toBeVisible();
    await user.click(screen.getByRole('checkbox', { name: 'Chọn clip Clip a' }));
    expect(screen.getByText('1 clip, tổng 15 s · Chưa đủ 20 s: chọn thêm clip')).toBeVisible();
    await waitFor(() => expect(saves.length).toBeGreaterThan(0));
    const saved = saves[saves.length - 1].background as { mode: string; clip_ids: string[] };
    expect(saved).toMatchObject({ mode: 'manual', clip_ids: ['b'] });
  });

  it('points to the library when it is empty', async () => {
    backend(postv(), []);
    app('/postv/bai/preview');
    expect(await screen.findByText('Thư viện nền đang trống.')).toBeVisible();
    expect(screen.getByRole('link', { name: 'Mở thư viện nền' })).toHaveAttribute('href', '/postv');
  });

  it('previews the hook, the post and each picked comment with the real card image', async () => {
    const user = userEvent.setup();
    backend(postv(), [clip('a')]);
    app('/postv/bai/preview');
    const aside = await screen.findByRole('complementary', { name: 'Xem trước thẻ' });
    const src = () => new URL(within(aside).getByRole('img').getAttribute('src') ?? '', 'http://x');
    expect(src().searchParams.get('kind')).toBe('hook');
    const chips = within(aside)
      .getAllByRole('button')
      .map((b) => b.textContent);
    expect(chips[0]).toMatch(/^Xem nhanh/);
    expect(chips.slice(3)).toEqual(['Tiêu đề', 'Bài gốc', 'user_b']); // chỉ bình luận đã chọn
    await user.click(within(aside).getByRole('button', { name: 'Bài gốc' }));
    expect(src().searchParams.get('kind')).toBe('post');
    await user.click(within(aside).getByRole('button', { name: 'user_b' }));
    expect([src().searchParams.get('kind'), src().searchParams.get('ref')]).toEqual([
      'comment',
      'c1',
    ]);
  });

  it('edits the hook text and accent, saves them, and reloads the card image after saving', async () => {
    const user = userEvent.setup();
    const saves = backend(postv(), []);
    app('/postv/bai/preview');
    const aside = await screen.findByRole('complementary', { name: 'Xem trước thẻ' });
    const version = () =>
      new URL(
        within(aside).getByRole('img').getAttribute('src') ?? '',
        'http://x',
      ).searchParams.get('v');
    const before = version();
    await user.type(screen.getByLabelText('Chữ thẻ tiêu đề'), 'Quên ví ở quán');
    await user.type(screen.getByLabelText('Cụm nhấn (ô màu)'), 'quên ví');
    await waitFor(() => expect(saves.length).toBeGreaterThan(0));
    expect(saves[saves.length - 1].hook).toEqual({ text: 'Quên ví ở quán', accent: 'quên ví' });
    await waitFor(() => expect(version()).not.toBe(before));
    expect(screen.getByPlaceholderText('Để trống: lấy câu đầu của bài')).toBeVisible();
  });

  it('chooses the card animation, and "Xem nhanh" waits for a voice file', async () => {
    const user = userEvent.setup();
    const saves = backend(postv(), []);
    app('/postv/bai/preview');
    expect(await screen.findByRole('button', { name: 'Mượt' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await user.click(screen.getByRole('button', { name: 'Nảy' }));
    expect(screen.getByRole('button', { name: 'Nảy' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Mượt' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: /^Xem nhanh/ })).toBeDisabled();
    await waitFor(() => expect(saves.length).toBeGreaterThan(0));
    expect((saves[saves.length - 1].settings as { card_animation: string }).card_animation).toBe(
      'bounce',
    );
  });

  it('allows deleting a background clip with confirmation', async () => {
    const user = userEvent.setup();
    const deleted = vi.fn(() => new Response(null, { status: 204 }));
    backend(postv(), [clip('c1', { title: 'Clip Thử Nghiệm' })], {
      'GET /api/projects': [postv()],
      'DELETE /api/backgrounds/c1': deleted,
    });
    app('/postv');
    const libCard = await screen.findByRole('region', { name: 'Thư viện nền' });
    const clipTitle = await within(libCard).findByText('Clip Thử Nghiệm');
    const clipItem = clipTitle.closest('li')!;
    const delBtn = within(clipItem).getByRole('button', { name: /Xoá Clip Thử Nghiệm/ });
    await user.click(delBtn);

    const dialog = await screen.findByRole('alertdialog', { name: 'Xoá clip nền' });
    expect(within(dialog).getByText(/Bạn có chắc muốn xoá clip "Clip Thử Nghiệm"\?/)).toBeVisible();

    await user.click(within(dialog).getByRole('button', { name: 'Xoá' }));
    expect(deleted).toHaveBeenCalledTimes(1);
  });
});
