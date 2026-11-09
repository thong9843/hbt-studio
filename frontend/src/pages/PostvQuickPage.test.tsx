import { act, screen, waitFor } from '@testing-library/react';
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
    last_render: { video: '/renders/bai-cu/video.mp4', duration: 60 },
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
      'GET /api/postv/settings': { voice_id: 'adam-bua' },
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
      const select = screen.getByRole('combobox');
      expect(select).toHaveValue('adam-bua');
    });
    expect(screen.getByText(/Bình luận: Tự động/)).toBeInTheDocument();
    expect(screen.getByText('75 s')).toBeInTheDocument();
    expect(screen.getByText('Nhạc: Tự chọn')).toBeInTheDocument();
    expect(screen.getByText('60 fps')).toBeInTheDocument();
    expect(screen.getByText('Outro: Bật')).toBeInTheDocument();

    // Cột trái video gần đây
    expect(await screen.findByText('Bài cũ Threads')).toBeInTheDocument();
  });

  it('enables submit button upon typing, submits on Enter and sends options', async () => {
    const user = userEvent.setup();
    const sent = {
      body: null as {
        url?: string;
        options?: { fps?: number; target_seconds?: number; pick_mode?: string };
      } | null,
    };

    stubFetch({
      'GET /api/projects': defaultProjects,
      'GET /api/voices': defaultVoices,
      'GET /api/postv/settings': { voice_id: 'adam-bua' },
      'GET /api/gd2/voice/preferences': { voice_id: 'adam-bua' },
      'GET /api/jobs': [],
      'POST /api/postv/auto': async (_url: string, init?: RequestInit) => {
        sent.body = JSON.parse(init?.body as string);
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
      expect(sent.body).not.toBeNull();
    });
    expect(sent.body?.url).toBe('https://www.threads.net/@user/post/xyz');
    expect(sent.body?.options?.fps).toBe(60);
    expect(sent.body?.options?.target_seconds).toBe(75);
    expect(sent.body?.options?.pick_mode).toBe('auto');
  });

  it('detects existing link and shows duplicate dialog, with open existing or force new', async () => {
    const user = userEvent.setup();
    let secondCallForceNew = false;

    stubFetch({
      'GET /api/projects': defaultProjects,
      'GET /api/voices': defaultVoices,
      'GET /api/postv/settings': { voice_id: 'adam-bua' },
      'GET /api/gd2/voice/preferences': { voice_id: 'adam-bua' },
      'GET /api/jobs': [],
      'POST /api/postv/auto': async (_url: string, init?: RequestInit) => {
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
      'GET /api/postv/settings': { voice_id: 'adam-bua' },
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
      'GET /api/postv/settings': { voice_id: 'adam-bua' },
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
          video: '/api/files/renders/job-done-123/video.mp4',
          cover: '/api/files/renders/job-done-123/cover.jpg',
          publish: '/api/files/renders/job-done-123/publish.txt',
          duration: 72.5,
          fps: 60,
          project_slug: 'postv-done',
        },
      });
    });

    // Thẻ kết quả
    expect(await screen.findByText('Video đã hoàn tất!')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Tải video' })).toHaveAttribute(
      'href',
      '/api/files/renders/job-done-123/video.mp4',
    );
    expect(screen.getByRole('button', { name: 'Sao chép nội dung đăng' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Tải ảnh bìa' })).toHaveAttribute(
      'href',
      '/api/files/renders/job-done-123/cover.jpg',
    );
    expect(screen.getByRole('link', { name: 'Chỉnh chi tiết' })).toHaveAttribute(
      'href',
      '/postv/postv-done/export',
    );
    expect(screen.getByRole('button', { name: 'Làm lại với tuỳ chọn khác' })).toBeInTheDocument();
  });

  it('supports manual comment picking when job pauses at waiting_pick', async () => {
    const user = userEvent.setup();
    const pickSent = {
      body: null as { comment_ids?: string[] } | null,
    };

    stubFetch({
      'GET /api/projects': defaultProjects,
      'GET /api/voices': defaultVoices,
      'GET /api/postv/settings': { voice_id: 'adam-bua' },
      'GET /api/gd2/voice/preferences': { voice_id: 'adam-bua' },
      'GET /api/jobs': [],
      'POST /api/postv/auto': {
        project_slug: 'postv-manual-slug',
        job_id: 'job-manual-1',
        existing_slug: null,
      },
      'POST /api/postv/auto/job-manual-1/pick': async (_url: string, init?: RequestInit) => {
        pickSent.body = JSON.parse(init?.body as string);
        return json({ ok: true, job_id: 'job-manual-1' });
      },
    });

    page();

    // Đổi chip Bình luận sang Tự chọn
    const pickModeChip = await screen.findByText(/Bình luận: Tự động/);
    await user.click(pickModeChip);
    expect(await screen.findByText(/Bình luận: Tự chọn/)).toBeInTheDocument();

    const textarea = screen.getByPlaceholderText('Dán link bài Threads hoặc dán chữ bài…');
    await user.type(textarea, 'Bài viết cần chọn bình luận thủ công');
    await user.click(screen.getByRole('button', { name: 'Tạo video' }));

    expect(await screen.findByText('Tiến trình tạo video')).toBeInTheDocument();
    await waitFor(() => expect(FakeEventSource.instances.length).toBeGreaterThan(0));

    // SSE phát sự kiện waiting_pick
    const es = FakeEventSource.instances[0];
    act(() => {
      es.emit('progress', {
        stage: 'pick',
        status: 'waiting_pick',
        progress: 1.0,
        message: 'Chờ chọn bình luận',
        data: {
          handle: 'tacgia_goc',
          post_text: 'Nội dung bài viết tác giả gốc cực hay ho và hấp dẫn.',
          target_seconds: 60,
          estimated_seconds: 25,
          comments: [
            {
              id: 'c1',
              handle: 'nguoixem1',
              text: 'Bình luận được đề xuất hay ho.',
              likes: 120,
              picked: true,
              filter_reason: null,
            },
            {
              id: 'c2',
              handle: 'nguoixem2',
              text: 'Ngắn',
              likes: 5,
              picked: false,
              filter_reason: 'ngắn',
            },
            {
              id: 'c3',
              handle: 'nguoixem3',
              text: 'Bình luận trùng lặp nội dung.',
              likes: 12,
              picked: false,
              filter_reason: 'trùng',
            },
          ],
        },
      });
    });

    // Bảng chọn bình luận hiện ra
    expect(await screen.findByText('Tự chọn bình luận cho video')).toBeInTheDocument();
    expect(screen.getByText('Bài viết gốc')).toBeInTheDocument();
    expect(screen.getByText(/Nội dung bài viết tác giả gốc/)).toBeInTheDocument();

    // Danh sách bình luận
    expect(screen.getByText('@nguoixem1')).toBeInTheDocument();
    expect(screen.getByText('@nguoixem2')).toBeInTheDocument();
    expect(screen.getByText(/Lọc:\s*ngắn/)).toBeInTheDocument();
    expect(screen.getByText(/Lọc:\s*trùng/)).toBeInTheDocument();

    // Bấm chọn thêm bình luận c2 (dù bị lọc vẫn tích được)
    const checkboxes = screen.getAllByRole('checkbox');
    // checkbox 0: post (disabled), checkbox 1: c1 (checked), checkbox 2: c2, checkbox 3: c3
    await user.click(checkboxes[2]);

    // Bấm Tạo video để gửi danh sách chọn
    const submitPickBtn = screen.getByRole('button', { name: 'Tạo video' });
    await user.click(submitPickBtn);

    await waitFor(() => {
      expect(pickSent.body).not.toBeNull();
    });
    expect(pickSent.body?.comment_ids).toContain('c1');
    expect(pickSent.body?.comment_ids).toContain('c2');
  });

  it('supports voice dropdown change and preview audio playback', async () => {
    const user = userEvent.setup();
    const settingsSent = {
      body: null as { voice_id?: string } | null,
    };

    stubFetch({
      'GET /api/projects': defaultProjects,
      'GET /api/voices': defaultVoices,
      'GET /api/postv/settings': { voice_id: 'adam-bua' },
      'GET /api/gd2/voice/preferences': { voice_id: 'adam-bua' },
      'GET /api/jobs': [],
      'POST /api/postv/settings': async (_url: string, init?: RequestInit) => {
        settingsSent.body = JSON.parse(init?.body as string);
        return json({ voice_id: settingsSent.body?.voice_id });
      },
    });

    page();

    await waitFor(() => {
      const select = screen.getByRole('combobox');
      expect(select).toHaveValue('adam-bua');
    });
    const voiceSelect = screen.getByRole('combobox');

    // Đổi giọng sang Mai Anh
    await user.selectOptions(voiceSelect, 'mai-anh');
    expect(voiceSelect).toHaveValue('mai-anh');

    await waitFor(() => {
      expect(settingsSent.body).not.toBeNull();
    });
    expect(settingsSent.body?.voice_id).toBe('mai-anh');

    // Nút nghe thử hiện diện
    const previewBtn = screen.getByTitle('Nghe thử câu mẫu');
    expect(previewBtn).toBeInTheDocument();
  });

  it('provides three-dot menu on recent video cards with Open, Download and Delete confirmation', async () => {
    const user = userEvent.setup();
    let deleteCalled = false;

    stubFetch({
      'GET /api/projects': defaultProjects,
      'GET /api/voices': defaultVoices,
      'GET /api/postv/settings': { voice_id: 'adam-bua' },
      'GET /api/gd2/voice/preferences': { voice_id: 'adam-bua' },
      'GET /api/jobs': [],
      'DELETE /api/postv/bai-cu': () => {
        deleteCalled = true;
        return json({ ok: true });
      },
    });

    page();

    expect(await screen.findByText('Bài cũ Threads')).toBeInTheDocument();

    // Bấm nút ⋮ (ba chấm dọc)
    const moreBtn = screen.getByTitle('Tuỳ chọn');
    await user.click(moreBtn);

    // Menu bung ra
    expect(await screen.findByRole('menuitem', { name: 'Mở' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Tải video' })).toBeInTheDocument();
    const deleteBtn = screen.getByRole('menuitem', { name: 'Xoá' });
    expect(deleteBtn).toBeInTheDocument();

    // Bấm Xoá
    await user.click(deleteBtn);

    // Hộp xác nhận mở ra
    expect(await screen.findByText('Xoá video này?')).toBeInTheDocument();
    const confirmDeleteBtn = screen.getByRole('button', { name: 'Xoá' });
    await user.click(confirmDeleteBtn);

    await waitFor(() => {
      expect(deleteCalled).toBe(true);
    });
  });
});
