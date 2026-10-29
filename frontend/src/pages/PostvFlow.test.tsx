import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { NewProjectProvider } from '../components/NewProjectDialog';
import { ToastProvider } from '../components/Toast';
import { stubFetch } from '../test/fakes';
import { project } from '../test/project';
import { renderWithProviders } from '../test/render';
import { PostvLayout } from './PostvLayout';
import { PostvPickPage } from './PostvPickPage';
import { PostvSoonPage } from './PostvSoonPage';
import { PostvSourcePage } from './PostvSourcePage';
import { ProjectsPage } from './ProjectsPage';

afterEach(() => vi.unstubAllGlobals());

const stats = { views: null, likes: null, replies: null, reposts: null, shares: null };
const comment = (id: string, over: Record<string, unknown> = {}) => ({
  id,
  handle: `user_${id}`,
  age: '14 giờ',
  text: `Bình luận ${id}`,
  parent: null,
  picked: false,
  ...stats,
  ...over,
});
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
  segments: [],
  ...over,
});

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

const CHECK = {
  seconds: 0,
  chars: 0,
  long: false,
  censored: 0,
  segments: [],
  issues: [],
};

/** Các route chung: đọc dự án, lưu (ghi lại thân gửi lên), kiểm tra kịch bản. */
function backend(initial: unknown, extra: Record<string, unknown> = {}) {
  const saves: Record<string, unknown>[] = [];
  const mock = stubFetch({
    'GET /api/projects/bai': initial,
    'PUT /api/projects/bai': (_url: string, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body));
      saves.push(body);
      return json(body);
    },
    'POST /api/projects/bai/postv/script/check': CHECK,
    ...extra,
  });
  return { saves, mock, last: () => saves[saves.length - 1] };
}

function app(path = '/postv/bai') {
  return renderWithProviders(
    <ToastProvider>
      <NewProjectProvider>
        <Routes>
          <Route path="/postv" element={<ProjectsPage kind="postv" />} />
          <Route path="/projects" element={<p>trang dự án</p>} />
          <Route path="/postv/:slug" element={<PostvLayout />}>
            <Route index element={<PostvSourcePage />} />
            <Route path="pick" element={<PostvPickPage />} />
            <Route path="script" element={<PostvSoonPage step={2} />} />
          </Route>
          <Route path="/p/:slug" element={<p>trình soạn cảnh</p>} />
        </Routes>
      </NewProjectProvider>
    </ToastProvider>,
    path,
  );
}

const PARSED = {
  guess: 'threads_text',
  source_url: 'https://www.threads.com/share/ABC/',
  post: { handle: 'moi_a', age: '25/08/2026', text: 'Bài mới tách ra' },
  comments: [
    {
      id: 'c1',
      handle: 'moi_b',
      age: '14 giờ',
      text: 'Ấm lòng ghê',
      same_author: false,
      picked: true,
    },
    { id: 'c2', handle: 'moi_c', age: '13 giờ', text: 'Hay quá', same_author: false, picked: true },
  ],
  hints: [],
  warnings: [],
};

describe('PostvLayout: thanh bước ở đầu', () => {
  it('shows the title, the badge and a 5-step bar above the step content', async () => {
    backend(postv());
    app();
    expect(await screen.findByRole('heading', { level: 1, name: 'Bài đêm khuya' })).toBeVisible();
    const bar = screen.getByRole('navigation', { name: 'Các bước' });
    const links = within(bar).getAllByRole('link');
    expect(links.map((a) => a.getAttribute('href'))).toEqual([
      '/postv/bai',
      '/postv/bai/pick',
      '/postv/bai/script',
      '/postv/bai/preview',
      '/postv/bai/export',
    ]);
    expect(links[0]).toHaveAttribute('aria-current', 'page');
    expect(links[0]).toHaveAccessibleName('Bước 1/5: Nguồn');
    // thanh bước nằm trước nội dung của bước
    const content = screen.getByRole('region', { name: 'Dán nội dung' });
    expect(bar.compareDocumentPosition(content) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Tất cả dự án' })).toHaveAttribute('href', '/postv');
  });

  it('moves between steps with the bar and marks the current one', async () => {
    const user = userEvent.setup();
    backend(postv({ comments: [comment('c1')] }));
    app();
    await screen.findByRole('region', { name: 'Dán nội dung' });
    await user.click(screen.getByRole('link', { name: 'Bước 2/5: Chọn đoạn' }));
    expect(await screen.findByRole('region', { name: 'Thứ tự trong video' })).toBeVisible();
    expect(screen.getByRole('link', { name: 'Bước 2/5: Chọn đoạn' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    await user.click(screen.getByRole('link', { name: 'Bước 3/5: Kịch bản' }));
    expect(await screen.findByText('Sắp có')).toBeVisible();
  });

  it('sends a video project to the scene editor', async () => {
    stubFetch({ 'GET /api/projects/bai': project({ slug: 'bai', title: 'Muỗi' }) });
    app();
    expect(await screen.findByText('trình soạn cảnh')).toBeVisible();
  });

  it('shows the error and a way back when the project cannot be read', async () => {
    stubFetch({ 'GET /api/projects/bai': () => json({ detail: 'Không có project' }, 404) });
    app();
    expect(await screen.findByRole('alert')).toBeVisible();
    expect(screen.getByRole('link', { name: 'Tất cả dự án' })).toHaveAttribute('href', '/postv');
  });
});

describe('Bước 1 · Nhập nguồn', () => {
  it('splits pasted text, fills the post and the comments, and saves them', async () => {
    const user = userEvent.setup();
    const { last } = backend(postv({ post: { ...postv().post, text: '' } }), {
      'POST /api/postv/parse': PARSED,
    });
    app();
    await user.type(await screen.findByLabelText('Chữ đã copy'), 'moi_a 17h ...');
    await user.click(screen.getByRole('button', { name: 'Tách bài' }));
    await waitFor(() => expect(screen.getByLabelText('Tên tài khoản')).toHaveValue('moi_a'));
    expect(screen.getByLabelText('Thời gian')).toHaveValue('25/08/2026');
    expect(screen.getByText('1 bài · 2 bình luận')).toBeVisible();
    expect(screen.getByLabelText('Tên tài khoản c1')).toHaveValue('moi_b');
    expect(screen.getByLabelText('Link bài · chỉ lưu làm dòng nguồn')).toHaveValue(
      'https://www.threads.com/share/ABC/',
    );
    await user.click(screen.getByRole('button', { name: 'Tiếp: Chọn đoạn' }));
    await screen.findByRole('region', { name: 'Thứ tự trong video' });
    const saved = last();
    expect((saved.post as { text: string }).text).toBe('Bài mới tách ra');
    expect(
      (saved.comments as { id: string; picked: boolean }[]).map((c) => [c.id, c.picked]),
    ).toEqual([
      ['c1', true],
      ['c2', true],
    ]);
    expect((saved.source as { url: string }).url).toBe('https://www.threads.com/share/ABC/');
  });

  it('asks before replacing a source that already has content', async () => {
    const user = userEvent.setup();
    backend(postv({ comments: [comment('c1')] }), { 'POST /api/postv/parse': PARSED });
    app();
    await user.type(await screen.findByLabelText('Chữ đã copy'), 'x');
    await user.click(screen.getByRole('button', { name: 'Tách bài' }));
    const dialog = await screen.findByRole('alertdialog', { name: 'Thay nội dung nguồn?' });
    await user.click(within(dialog).getByRole('button', { name: 'Huỷ' }));
    expect(screen.getByLabelText('Tên tài khoản')).toHaveValue('tac_gia');
    await user.click(screen.getByRole('button', { name: 'Tách bài' }));
    await user.click(
      within(await screen.findByRole('alertdialog', { name: 'Thay nội dung nguồn?' })).getByRole(
        'button',
        {
          name: 'Thay',
        },
      ),
    );
    await waitFor(() => expect(screen.getByLabelText('Tên tài khoản')).toHaveValue('moi_a'));
  });

  it('shows the warnings and changes nothing when the text is not recognised', async () => {
    const user = userEvent.setup();
    backend(postv(), {
      'POST /api/postv/parse': {
        guess: 'unknown',
        source_url: null,
        post: null,
        comments: [],
        hints: [],
        warnings: ['Không nhận ra bài hay bình luận nào. Hãy sửa tay hoặc dán lại.'],
      },
    });
    app();
    await user.type(await screen.findByLabelText('Chữ đã copy'), 'xin chào');
    await user.click(screen.getByRole('button', { name: 'Tách bài' }));
    expect(await screen.findByText(/Không nhận ra bài hay bình luận nào/)).toBeVisible();
    expect(screen.getByLabelText('Tên tài khoản')).toHaveValue('tac_gia');
  });

  it('embed code only gives the link: stored, never opened by the app', async () => {
    const user = userEvent.setup();
    const { mock } = backend(postv(), {
      'POST /api/postv/parse': {
        guess: 'embed',
        source_url: 'https://www.threads.com/@u/post/X',
        post: null,
        comments: [],
        hints: [],
        warnings: ['Mã nhúng chỉ chứa liên kết, không có chữ. Hãy dán chữ của bài.'],
      },
    });
    app();
    await user.type(await screen.findByLabelText('Chữ đã copy'), '<blockquote ...>');
    await user.click(screen.getByRole('button', { name: 'Tách bài' }));
    expect(await screen.findByText(/Mã nhúng chỉ chứa liên kết/)).toBeVisible();
    expect(screen.getByLabelText('Link bài · chỉ lưu làm dòng nguồn')).toHaveValue(
      'https://www.threads.com/@u/post/X',
    );
    const urls = mock.mock.calls.map((c) => String(c[0]));
    expect(urls.some((u) => u.includes('threads.com'))).toBe(false); // không gọi ra ngoài
    expect(urls.every((u) => u.startsWith('/api/'))).toBe(true);
  });

  it('"Mở bài" opens the saved link in a new tab, and only for http(s) links', async () => {
    const user = userEvent.setup();
    backend(
      postv({ source: { url: 'https://www.threads.com/share/ABC/', note: '', pasted_at: null } }),
    );
    app();
    const link = await screen.findByRole('link', { name: 'Mở bài' });
    expect(link).toHaveAttribute('href', 'https://www.threads.com/share/ABC/');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    const input = screen.getByLabelText('Link bài · chỉ lưu làm dòng nguồn');
    await user.clear(input);
    await user.type(input, 'javascript:alert(1)');
    expect(screen.queryByRole('link', { name: 'Mở bài' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Mở bài' })).toBeDisabled();
  });

  it('reads 27,6K / 1.8K / 351 into numbers for the post stats and shows them on the card', async () => {
    const user = userEvent.setup();
    const { saves } = backend(postv());
    app();
    const likes = await screen.findByRole('textbox', { name: /^Thích/ });
    await user.type(likes, '27,6K');
    await user.type(screen.getByRole('textbox', { name: /^Bình luận/ }), '351');
    await user.type(screen.getByRole('textbox', { name: /^Chia sẻ/ }), '1.8K');
    await user.click(screen.getByRole('button', { name: 'Tiếp: Chọn đoạn' }));
    await screen.findByRole('region', { name: 'Thứ tự trong video' });
    const post = saves[saves.length - 1].post as Record<string, number>;
    expect([post.likes, post.replies, post.shares]).toEqual([27600, 351, 1800]);
  });

  it('previews the real server-drawn card and flags an unreadable number', async () => {
    const user = userEvent.setup();
    backend(postv({ post: { ...postv().post, likes: 27600, replies: 351, views: 619000 } }));
    app();
    const preview = await screen.findByRole('complementary', { name: 'Xem trước thẻ bài gốc' });
    const img = within(preview).getByRole('img', { name: 'Xem trước thẻ bài gốc' });
    const url = new URL(img.getAttribute('src') ?? '', 'http://x');
    expect(url.pathname).toBe('/api/projects/bai/postv/card.png');
    expect([url.searchParams.get('kind'), url.searchParams.get('w')]).toEqual(['post', '288']);
    expect(url.searchParams.has('v')).toBe(true); // đổi sau mỗi lần lưu để tải lại ảnh
    const shares = screen.getByRole('textbox', { name: /^Chia sẻ/ });
    await user.type(shares, 'abc');
    expect(shares).toHaveAttribute('aria-invalid', 'true');
  });

  it('marks the three required stats', async () => {
    backend(postv());
    app();
    await screen.findByRole('region', { name: 'Kết quả tách' });
    for (const name of [/^Thích/, /^Bình luận/, /^Chia sẻ/]) {
      expect(screen.getByRole('textbox', { name })).toBeRequired();
    }
    expect(screen.getByRole('textbox', { name: /^Đăng lại/ })).not.toBeRequired();
    expect(screen.getByRole('textbox', { name: /^Lượt xem/ })).not.toBeRequired();
  });

  it('asks whether a lone number line is the like count, and applies it on "Đúng"', async () => {
    const user = userEvent.setup();
    backend(postv({ post: { ...postv().post, text: '' } }), {
      'POST /api/postv/parse': {
        ...PARSED,
        hints: [{ block: 1, raw: '1.2K', value: 1200 }],
        warnings: ['Có 1 dòng chỉ gồm số, có thể là số liệu: bạn kiểm lại.'],
      },
    });
    app();
    await user.type(await screen.findByLabelText('Chữ đã copy'), 'x');
    await user.click(screen.getByRole('button', { name: 'Tách bài' }));
    const ask = await screen.findByRole('group', { name: 'Dòng "1.2K" của moi_b là số like?' });
    await user.click(within(ask).getByRole('button', { name: 'Đúng' }));
    expect(screen.getByLabelText('Số thích của moi_b')).toHaveValue('1,2K');
    expect(screen.queryByRole('group', { name: /là số like/ })).toBeNull();
  });

  it('edits, adds, removes comments and swaps one into the original post', async () => {
    const user = userEvent.setup();
    const { saves } = backend(postv({ comments: [comment('c1'), comment('c2')] }));
    app();
    await user.type(await screen.findByLabelText('Tên tài khoản c1'), '_sua');
    await user.click(screen.getByRole('button', { name: 'Thêm bình luận' }));
    expect(screen.getByLabelText('Tên tài khoản c3')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Thao tác: user_c2' }));
    await user.click(screen.getByRole('menuitem', { name: 'Xoá' }));
    expect(screen.queryByLabelText('Tên tài khoản c2')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Thao tác: user_c1_sua' }));
    await user.click(screen.getByRole('menuitem', { name: 'Đặt làm bài gốc' }));
    expect(screen.getByLabelText('Tên tài khoản')).toHaveValue('user_c1_sua');
    // bài gốc cũ trở thành bình luận
    const old = await screen.findAllByLabelText(/^Tên tài khoản c\d$/);
    expect(old.map((i) => (i as HTMLInputElement).value)).toContain('tac_gia');
    await user.click(screen.getByRole('button', { name: 'Tiếp: Chọn đoạn' }));
    await screen.findByRole('region', { name: 'Thứ tự trong video' });
    expect((saves[saves.length - 1].post as { handle: string }).handle).toBe('user_c1_sua');
  });

  it('keeps "Tiếp" off until the post has text', async () => {
    backend(postv({ post: { ...postv().post, text: '' } }));
    app();
    const next = await screen.findByRole('button', { name: 'Tiếp: Chọn đoạn' });
    expect(next).toBeDisabled();
    expect(next).toHaveAttribute('title', 'Cần có chữ bài gốc trước');
  });

  it('shows how many words will be censored and how many only remind', async () => {
    backend(postv(), {
      'POST /api/projects/bai/postv/script/check': {
        ...CHECK,
        censored: 2,
        issues: [{ where: 'Bài gốc', level: 'warn', message: 'x', word: 'bia' }],
      },
    });
    app();
    expect(await screen.findByText('2 từ sẽ bị che (bíp + làm mờ) · 1 từ nhắc')).toBeVisible();
  });
});

describe('Bước 2 · Chọn đoạn', () => {
  const three = [
    comment('c1', { likes: 5, picked: true }),
    comment('c2', { likes: 900, picked: true }),
    comment('c3', { likes: 1200, picked: false }),
    comment('c4', { likes: 20, picked: false }),
  ];

  it('builds the segment list on entry: hook, post, picked comments, commentary', async () => {
    const { saves } = backend(postv({ comments: three }));
    app('/postv/bai/pick');
    const order = await screen.findByRole('region', { name: 'Thứ tự trong video' });
    const items = within(order).getAllByRole('listitem');
    expect(items.map((li) => li.textContent?.replace(/\d+≈.*|—$/, ''))).toEqual([
      expect.stringContaining('Hook'),
      expect.stringContaining('Bài gốc'),
      expect.stringContaining('Bình luận'),
      expect.stringContaining('Bình luận'),
      expect.stringContaining('Góc nhìn'),
    ]);
    expect(screen.getByText('Bài gốc + 2/4')).toBeVisible();
    expect(screen.getByText('5 đoạn · 4 thẻ')).toBeVisible();
    await waitFor(() => expect(saves.length).toBeGreaterThan(0)); // tự lưu sau 1 s
  });

  it('toggles a comment: its segment appears and disappears', async () => {
    const user = userEvent.setup();
    backend(postv({ comments: three }));
    app('/postv/bai/pick');
    const order = await screen.findByRole('region', { name: 'Thứ tự trong video' });
    expect(within(order).getAllByRole('listitem')).toHaveLength(5);
    await user.click(screen.getByRole('checkbox', { name: 'Chọn bình luận của user_c3' }));
    expect(within(order).getAllByRole('listitem')).toHaveLength(6);
    await user.click(screen.getByRole('checkbox', { name: 'Chọn bình luận của user_c1' }));
    expect(within(order).getAllByRole('listitem')).toHaveLength(5);
  });

  it('"Gợi ý theo like" picks the three most liked, "Bỏ chọn hết" clears', async () => {
    const user = userEvent.setup();
    backend(postv({ comments: three }));
    app('/postv/bai/pick');
    await screen.findByRole('region', { name: 'Thứ tự trong video' });
    await user.click(screen.getByRole('button', { name: 'Gợi ý theo like' }));
    const checked = (name: string) =>
      (screen.getByRole('checkbox', { name: `Chọn bình luận của ${name}` }) as HTMLInputElement)
        .checked;
    expect([
      checked('user_c1'),
      checked('user_c2'),
      checked('user_c3'),
      checked('user_c4'),
    ]).toEqual([false, true, true, true]);
    expect(screen.getByText('Bài gốc + 3/4')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Bỏ chọn hết' }));
    expect(screen.getByText('Bài gốc + 0/4')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Bỏ chọn hết' })).toBeDisabled();
  });

  it('reorders comments with the up/down buttons (first up and last down are off)', async () => {
    const user = userEvent.setup();
    backend(postv({ comments: three }));
    app('/postv/bai/pick');
    await screen.findByRole('region', { name: 'Thứ tự trong video' });
    expect(screen.getByRole('button', { name: 'Đưa user_c1 lên' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Đưa user_c4 xuống' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Đưa user_c2 lên' }));
    const names = within(screen.getByRole('list', { name: 'Bình luận' }))
      .getAllByRole('checkbox')
      .map((c) => c.getAttribute('aria-label'));
    expect(names).toEqual([
      'Chọn bình luận của user_c2',
      'Chọn bình luận của user_c1',
      'Chọn bình luận của user_c3',
      'Chọn bình luận của user_c4',
    ]);
  });

  it('estimates the duration from the voice text and only reminds from 120 s', async () => {
    const long = 'x'.repeat(2000); // 2000 / 16,5 ≈ 121 s
    backend(
      postv({
        comments: [comment('c1', { picked: true })],
        segments: [
          { role: 'hook', card: 'hook', voice: '', ref: null },
          { role: 'post', card: 'post', voice: long, ref: null },
          { role: 'comment', card: 'comment', voice: 'Ngắn', ref: 'c1' },
          { role: 'commentary', card: 'none', voice: '', ref: null },
        ],
      }),
    );
    app('/postv/bai/pick');
    expect(await screen.findByText('Dài từ 120 s, nên dưới 2 phút')).toBeVisible();
    expect(screen.getByText('≈ 121 s')).toBeVisible();
  });

  it('does not nag before 120 s and has no commentary / copy warnings', async () => {
    backend(postv({ comments: [comment('c1', { picked: true })] }));
    app('/postv/bai/pick');
    expect(await screen.findByText('Nhắc khi từ 120 s')).toBeVisible();
    expect(screen.queryByText(/nguyên văn|tỉ lệ biến đổi|góc nhìn kênh/i)).toBeNull();
  });

  it('says when there are no comments, and goes on to the next step', async () => {
    const user = userEvent.setup();
    backend(postv());
    app('/postv/bai/pick');
    expect(
      await screen.findByText('Chưa có bình luận. Quay lại bước Nguồn để thêm.'),
    ).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Tiếp: Kịch bản' }));
    expect(await screen.findByText('Sắp có')).toBeVisible();
  });
});

describe('Trang /postv', () => {
  const summary = (slug: string, title: string, kind: string) => ({
    slug,
    title,
    kind,
    updated_at: '2026-10-29T10:00:00',
    thumb: null,
    cover: null,
    last_render: null,
    last_final: null,
    error: null,
  });

  it('lists only PostV projects and opens the create dialog on PostV', async () => {
    const user = userEvent.setup();
    stubFetch({
      'GET /api/projects': [summary('bai', 'Bài PostV', 'postv'), summary('muoi', 'Muỗi', 'video')],
    });
    app('/postv');
    expect(await screen.findByRole('heading', { level: 1, name: 'PostV' })).toBeVisible();
    expect(await screen.findByText(/1 video/)).toBeVisible();
    expect(screen.getByRole('link', { name: 'Mở: Bài PostV' })).toHaveAttribute(
      'href',
      '/postv/bai',
    );
    expect(screen.queryByText('Muỗi')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Tạo PostV' }));
    const dialog = await screen.findByRole('dialog', { name: 'Tạo video mới' });
    expect(within(dialog).getByRole('button', { name: 'PostV' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('shows an empty state with a create button when there is no PostV yet', async () => {
    const user = userEvent.setup();
    stubFetch({ 'GET /api/projects': [summary('muoi', 'Muỗi', 'video')] });
    app('/postv');
    expect(await screen.findByRole('heading', { name: 'Chưa có PostV nào' })).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Tạo PostV' }));
    const dialog = await screen.findByRole('dialog', { name: 'Tạo video mới' });
    expect(within(dialog).getByRole('button', { name: 'PostV' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });
});
