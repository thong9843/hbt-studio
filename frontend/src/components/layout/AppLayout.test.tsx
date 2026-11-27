import { act, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useRef } from 'react';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useRenderJobStatus } from '../../hooks/renderJob';
import { resetActiveStreams } from '../../hooks/useJob';
import { AppLayout } from './AppLayout';
import { ToastProvider } from '../Toast';
import { HbtCorePage } from '../../pages/HbtCorePage';
import { FakeEventSource, stubFetch } from '../../test/fakes';
import { renderWithProviders } from '../../test/render';

afterEach(() => vi.unstubAllGlobals());

const health = {
  ok: true,
  ffmpeg: true,
  whisper: false,
  gpu: false,
  vieneu: true,
  vieneu_note: null,
  missing: [],
};

const assetsMock = {
  topics: ['history', 'fun', 'science', 'mystery'],
  sfx: [],
  sfx_presets: ['whoosh', 'pop', 'impact', 'none'],
  topic_music: { history: [], fun: [], science: [], mystery: [] },
  images: [],
  gemini_configured: true,
};

const geminiModelsMock = {
  models: [{ id: 'gemini-3.8-flash', name: 'Gemini 3.8 Flash (Mặc định / Nhanh)' }],
  default: 'gemini-3.8-flash',
};

describe('Unified Studio UI: AppLayout & Sidebar & HbtCorePage', () => {
  it('renders Sidebar with 5 ordered sections and preserves HBT Core prompt state across navigation', async () => {
    stubFetch({
      'GET /api/health': health,
      'GET /api/projects': [],
      'GET /api/hbt-core/assets': assetsMock,
      'GET /api/hbt/core/models': geminiModelsMock,
    });

    const user = userEvent.setup();
    renderWithProviders(
      <ToastProvider>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="/" element={<p>Dashboard Hub</p>} />
            <Route path="/core" element={<HbtCorePage />} />
            <Route path="/postv" element={<p>PostV Workspace</p>} />
            <Route path="/chatting" element={<p>Chatting Workspace</p>} />
            <Route path="/library" element={<p>Asset Hub Workspace</p>} />
            <Route path="/settings" element={<p>Settings Workspace</p>} />
          </Route>
        </Routes>
      </ToastProvider>,
      '/core',
    );

    const nav = screen.getByRole('navigation', { name: 'Điều hướng chính' });
    const links = within(nav).getAllByRole('link');
    expect(links.map((a) => a.textContent)).toEqual([
      'Trang chủ',
      'HBT Core',
      'PostV',
      'Chatting',
      'StickV',
      'Thư viện',
    ]);

    // Thanh Prompt thông minh hiển thị trực tiếp (Prompt-first)
    const promptInput = await screen.findByLabelText('Câu nhắc 1-Click Prompt');
    await user.type(promptInput, 'Bí ẩn Kim tự tháp Ai Cập');
    expect(promptInput).toHaveValue('Bí ẩn Kim tự tháp Ai Cập');

    // Chuyển sang phân hệ PostV, Chatting, Thư viện rồi quay lại HBT Core
    await user.click(within(nav).getByRole('link', { name: 'PostV' }));
    expect(await screen.findByText('PostV Workspace')).toBeVisible();

    await user.click(within(nav).getByRole('link', { name: 'Chatting' }));
    expect(await screen.findByText('Chatting Workspace')).toBeVisible();

    await user.click(within(nav).getByRole('link', { name: 'Thư viện' }));
    expect(await screen.findByText('Asset Hub Workspace')).toBeVisible();

    await user.click(within(nav).getByRole('link', { name: 'HBT Core' }));

    // Kiểm tra câu nhắc đang nhập vẫn được giữ nguyên
    expect(await screen.findByLabelText('Câu nhắc 1-Click Prompt')).toHaveValue(
      'Bí ẩn Kim tự tháp Ai Cập',
    );
  });

  it('shows SidebarRenderStatus across all 6 routes for all 4 engines (expanded & collapsed) with 0 route body re-renders', async () => {
    resetActiveStreams();
    FakeEventSource.instances = [];
    vi.stubGlobal('EventSource', FakeEventSource);
    stubFetch({
      'GET /api/health': health,
      'GET /api/projects': [],
      'GET /api/jobs': [],
    });

    let bodyRenderCount = 0;
    function RouteBody({ label }: { label: string }) {
      const ref = useRef(0);
      ref.current += 1;
      bodyRenderCount = ref.current;
      return <p>{label}</p>;
    }

    function TriggerAllEngines() {
      const job = useRenderJobStatus();
      return (
        <div className="space-x-2">
          <button
            type="button"
            onClick={() =>
              job.attachJob({
                jobId: 'job-core-1',
                slug: 'bai-core',
                kind: 'hbt_core_auto',
                engine: 'core',
                title: 'Bài Core 1',
                progress: 12,
                stage: 'Tạo kịch bản',
              })
            }
          >
            start-core
          </button>
          <button
            type="button"
            onClick={() =>
              job.attachJob({
                jobId: 'job-postv-1',
                slug: 'bai-postv',
                kind: 'postv_quick',
                engine: 'postv',
                title: 'Bài PostV 1',
                progress: 24,
                stage: 'Chọn bình luận',
              })
            }
          >
            start-postv
          </button>
          <button
            type="button"
            onClick={() =>
              job.attachJob({
                jobId: 'job-chat-1',
                slug: 'bai-chat',
                kind: 'chatting_render',
                engine: 'chatting',
                title: 'Bài Chat 1',
                progress: 35,
                stage: 'Dựng tin nhắn',
              })
            }
          >
            start-chatting
          </button>
          <button
            type="button"
            onClick={() =>
              job.attachJob({
                jobId: 'job-stickv-1',
                slug: 'pisa-demo',
                kind: 'stickv',
                engine: 'stickv',
                title: 'Tháp Pisa',
                progress: 40,
                stage: 'Dựng khung hình',
              })
            }
          >
            start-stickv
          </button>
        </div>
      );
    }

    const user = userEvent.setup();
    renderWithProviders(
      <ToastProvider>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="/" element={<TriggerAllEngines />} />
            <Route path="/core" element={<RouteBody label="Core Page" />} />
            <Route path="/postv" element={<RouteBody label="PostV Page" />} />
            <Route path="/chatting" element={<RouteBody label="Chatting Page" />} />
            <Route path="/stickv" element={<RouteBody label="StickV Page" />} />
            <Route path="/library" element={<RouteBody label="Library Page" />} />
          </Route>
        </Routes>
      </ToastProvider>,
      '/',
    );

    const nav = screen.getByRole('navigation', { name: 'Điều hướng chính' });

    // Kiểm 4 engine đều lên badge & route đúng trong SidebarRenderStatus
    await user.click(screen.getByRole('button', { name: 'start-core' }));
    let statusCard = await screen.findByRole('status', { name: 'Đang dựng' });
    expect(statusCard).toHaveTextContent('HBT Core');
    expect(within(statusCard).getByRole('link')).toHaveAttribute('href', '/core?slug=bai-core');

    await user.click(screen.getByRole('button', { name: 'start-postv' }));
    statusCard = await screen.findByRole('status', { name: 'Đang dựng' });
    expect(statusCard).toHaveTextContent('PostV');
    expect(within(statusCard).getByRole('link')).toHaveAttribute('href', '/postv');

    await user.click(screen.getByRole('button', { name: 'start-chatting' }));
    statusCard = await screen.findByRole('status', { name: 'Đang dựng' });
    expect(statusCard).toHaveTextContent('Chatting');
    expect(within(statusCard).getByRole('link')).toHaveAttribute('href', '/chatting/bai-chat');

    await user.click(screen.getByRole('button', { name: 'start-stickv' }));
    statusCard = await screen.findByRole('status', { name: 'Đang dựng' });
    expect(statusCard).toHaveTextContent('StickV');
    expect(statusCard).toHaveTextContent('Tháp Pisa');
    expect(within(statusCard).getByRole('link')).toHaveAttribute(
      'href',
      '/stickv?slug=pisa-demo',
    );

    // Chuyển qua tất cả route kể cả /stickv -> SidebarRenderStatus LUÔN hiển thị và KHÔNG re-render trang khi % nhảy
    await user.click(within(nav).getByRole('link', { name: 'StickV' }));
    expect(await screen.findByText('StickV Page')).toBeVisible();
    expect(screen.getByRole('status', { name: 'Đang dựng' })).toHaveTextContent('Tháp Pisa');

    const rendersBeforeTicks = bodyRenderCount;
    const stickvEs = FakeEventSource.instances[FakeEventSource.instances.length - 1];
    act(() => {
      stickvEs.emit('progress', { progress: 65, step: 'Dựng khung hình (Beat 5/10)', message: '' });
    });
    expect(bodyRenderCount).toBe(rendersBeforeTicks);
    expect(screen.getByRole('status', { name: 'Đang dựng' })).toHaveTextContent('65%');

    // Chuyển sang Thư viện & thu gọn Sidebar -> hiện vòng tròn SVG Icon Rail kèm 65%
    await user.click(within(nav).getByRole('link', { name: 'Thư viện' }));
    expect(await screen.findByText('Library Page')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Thu gọn thanh bên' }));
    const ring = screen.getByRole('progressbar', { name: 'Tiến độ dựng' });
    expect(ring).toHaveAttribute('aria-valuenow', '65');
    expect(ring).toHaveTextContent('65%');
    resetActiveStreams();
  });
});
