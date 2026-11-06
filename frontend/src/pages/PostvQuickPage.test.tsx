import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { FakeEventSource, json, stubFetch } from '../test/fakes';
import { renderWithProviders } from '../test/render';
import { PostvQuickPage } from './PostvQuickPage';

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal('EventSource', FakeEventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const defaultProjects = [
  {
    slug: 'bai-cu',
    title: 'Bài cũ Threads',
    kind: 'postv',
    updated_at: '2026-11-06T10:00:00',
    thumb: null,
    cover: null,
    last_render: null,
    last_final: null,
  },
];

const defaultVoices = {
  ok: true,
  provider: 'vieneu',
  voices: [
    { id: 'adam-bua', label: 'Adam bựa', gender: 'Nam', region: 'Bắc', style: 'Tự nhiên' },
    { id: 'mai-anh', label: 'Mai Anh', gender: 'Nữ', region: 'Bắc', style: 'Truyền cảm' },
  ],
};

function page() {
  return renderWithProviders(
    <Routes>
      <Route path="/postv" element={<PostvQuickPage />} />
      <Route path="/postv/:slug/export" element={<p>Màn chỉnh chi tiết</p>} />
      <Route path="/postv/:slug" element={<p>Màn chi tiết dự án</p>} />
    </Routes>,
    '/postv',
  );
}

describe('PostvQuickPage', () => {
  it('renders initial empty state with greeting, textarea, option chips and disabled submit button', async () => {
    stubFetch({
      'GET /api/projects': defaultProjects,
      'GET /api/voices': defaultVoices,
      'GET /api/gd2/voice/preferences': { voice_id: 'adam-bua' },
      'GET /api/jobs': [],
    });

    page();

    // Lời chào & ô nhập
    expect(await screen.findByText('Tạo video Threads')).toBeInTheDocument();
    const textarea = screen.getByPlaceholderText('Dán link bài Threads hoặc dán chữ bài…');
    expect(textarea).toBeInTheDocument();

    // Nút tạo video bị tắt khi ô nhập rỗng
    const submitBtn = screen.getByRole('button', { name: 'Tạo video' });
    expect(submitBtn).toBeDisabled();

    // Hàng chip tuỳ chọn
    await waitFor(() => {
      expect(screen.getByTitle('Bấm để đổi giọng')).toHaveTextContent(/Adam bựa/);
    });
    expect(screen.getByText('75 s')).toBeInTheDocument();
    expect(screen.getByText('Nhạc: Tự chọn')).toBeInTheDocument();
    expect(screen.getByText('60 fps')).toBeInTheDocument();
    expect(screen.getByText('Outro: Bật')).toBeInTheDocument();

    // Cột trái video gần đây
    expect(await screen.findByText('Bài cũ Threads')).toBeInTheDocument();
  });

  it('enables submit button upon typing, submits on Enter and sends options', async () => {
    const user = userEvent.setup();
    let sentBody: Record<string, unknown> | null = null;

    stubFetch({
      'GET /api/projects': defaultProjects,
      'GET /api/voices': defaultVoices,
      'GET /api/gd2/voice/preferences': { voice_id: 'adam-bua' },
      'GET /api/jobs': [],
      'POST /api/postv/auto': async (_url, init) => {
        sentBody = JSON.parse(init?.body as string);
        return json({
          project_slug: 'postv-threads-123',
          job_id: 'job-auto-123',
          existing_slug: null,
        });
      },
    });

    page();

    const textarea = await screen.findByPlaceholderText('Dán link bài Threads hoặc dán chữ bài…');
    const submitBtn = screen.getByRole('button', { name: 'Tạo video' });

    // Gõ link vào
    await user.type(textarea, 'https://www.threads.net/@user/post/xyz');
    expect(submitBtn).toBeEnabled();

    // Bấm Tạo video
    await user.click(submitBtn);

    await waitFor(() => {
      expect(sentBody).not.toBeNull();
    });
    expect(sentBody?.url).toBe('https://www.threads.net/@user/post/xyz');
    expect((sentBody?.options as Record<string, unknown>).fps).toBe(60);
    expect((sentBody?.options as Record<string, unknown>).target_seconds).toBe(75);
  });

  it('detects existing link and shows duplicate dialog, with open existing or force new', async () => {
    const user = userEvent.setup();
    let secondCallForceNew = false;

    stubFetch({
      'GET /api/projects': defaultProjects,
      'GET /api/voices': defaultVoices,
      'GET /api/gd2/voice/preferences': { voice_id: 'adam-bua' },
      'GET /api/jobs': [],
      'POST /api/postv/auto': async (_url, init) => {
        const body = JSON.parse(init?.body as string);
        if (body.force_new) {
          secondCallForceNew = true;
          return json({
            project_slug: 'bai-moi-force',
            job_id: 'job-force-1',
            existing_slug: null,
          });
        }
        return json({
          project_slug: 'bai-cu',
          existing_slug: 'bai-cu',
          job_id: null,
        });
      },
    });

    page();

    const textarea = await screen.findByPlaceholderText('Dán link bài Threads hoặc dán chữ bài…');
    await user.type(textarea, 'https://www.threads.net/@user/post/existing');
    await user.click(screen.getByRole('button', { name: 'Tạo video' }));

    // Hiện thông báo trùng
    expect(await screen.findByText('Bài viết đã từng làm video')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Mở video cũ' })).toBeInTheDocument();

    const forceBtn = screen.getByRole('button', { name: 'Làm mới' });
    await user.click(forceBtn);

    await waitFor(() => {
      expect(secondCallForceNew).toBe(true);
    });
  });

  it('handles running state with 6 stages, pick preview and progress bar', async () => {
    const user = userEvent.setup();

    stubFetch({
      'GET /api/projects': defaultProjects,
      'GET /api/voices': defaultVoices,
      'GET /api/gd2/voice/preferences': { voice_id: 'adam-bua' },
      'GET /api/jobs': [],
      'POST /api/postv/auto': {
        project_slug: 'postv-threads-123',
        job_id: 'job-running-123',
        existing_slug: null,
      },
      'POST /api/jobs/job-running-123/cancel': {
        id: 'job-running-123',
        status: 'cancelled',
      },
    });

    page();

    const textarea = await screen.findByPlaceholderText('Dán link bài Threads hoặc dán chữ bài…');
    await user.type(textarea, 'Bài viết dán trực tiếp');
    await user.click(screen.getByRole('button', { name: 'Tạo video' }));

    // Tiến trình 6 bước xuất hiện
    expect(await screen.findByText('Tiến trình tạo video')).toBeInTheDocument();
    expect(screen.getByText('Tải bài viết Threads')).toBeInTheDocument();
    expect(screen.getByText('Chọn bình luận hay')).toBeInTheDocument();
    expect(screen.getByText('Soạn kịch bản')).toBeInTheDocument();
    expect(screen.getByText('Sinh giọng đọc VieNeu')).toBeInTheDocument();
    expect(screen.getByText('Dựng video bản đẹp')).toBeInTheDocument();
    expect(screen.getByText('Hoàn tất')).toBeInTheDocument();

    // FakeEventSource phát sự kiện pick
    const es = FakeEventSource.instances[0];
    expect(es).toBeDefined();

    act(() => {
      es.emit('progress', {
        stage: 'pick',
        status: 'done',
        progress: 30,
        message: 'Đã chọn 3 bình luận',
        data: {
          handle: 'tacgia_threads',
          snippet: 'Đoạn đầu bài viết cực cuốn...',
          picked_count: 3,
          total_comments: 5,
        },
      });
    });

    expect(await screen.findByText('@tacgia_threads')).toBeInTheDocument();
    expect(screen.getByText(/Đã chọn 3\/5 bình luận/)).toBeInTheDocument();

    // Nút huỷ
    const cancelBtn = screen.getByRole('button', { name: 'Huỷ' });
    await user.click(cancelBtn);
  });

  it('renders completed result card with video player and action buttons', async () => {
    const user = userEvent.setup();

    stubFetch({
      'GET /api/projects': defaultProjects,
      'GET /api/voices': defaultVoices,
      'GET /api/gd2/voice/preferences': { voice_id: 'adam-bua' },
      'GET /api/jobs': [],
      'POST /api/postv/auto': {
        project_slug: 'postv-done',
        job_id: 'job-done-123',
        existing_slug: null,
      },
    });

    page();

    const textarea = await screen.findByPlaceholderText('Dán link bài Threads hoặc dán chữ bài…');
    await user.type(textarea, 'https://www.threads.net/@u/post/done');
    await user.click(screen.getByRole('button', { name: 'Tạo video' }));

    const es = FakeEventSource.instances[0];
    act(() => {
      es.emit('end', {
        status: 'done',
        output: {
          video: 'renders/job-done-123/video.mp4',
          cover: 'renders/job-done-123/cover.jpg',
          publish: 'renders/job-done-123/publish.txt',
          duration: 72.5,
          fps: 60,
          project_slug: 'postv-done',
        },
      });
    });

    // Thẻ kết quả
    expect(await screen.findByText('Video đã hoàn tất!')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Tải video' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sao chép nội dung đăng' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Tải ảnh bìa' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Chỉnh chi tiết' })).toHaveAttribute(
      'href',
      '/postv/postv-done/export',
    );
    expect(screen.getByRole('button', { name: 'Làm lại với tuỳ chọn khác' })).toBeInTheDocument();
  });
});
