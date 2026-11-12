import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AppLayout } from './AppLayout';
import { ToastProvider } from '../Toast';
import { HbtCorePage } from '../../pages/HbtCorePage';
import { stubFetch } from '../../test/fakes';
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
  it('renders Sidebar with all 5 core studio sections and preserves HBT Core state across navigation', async () => {
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
            <Route path="/projects" element={<p>Projects View</p>} />
            <Route path="/postv" element={<p>PostV Workspace</p>} />
            <Route path="/chatting" element={<p>Chatting Workspace</p>} />
            <Route path="/settings" element={<p>Settings Workspace</p>} />
          </Route>
        </Routes>
      </ToastProvider>,
      '/core',
    );

    const nav = screen.getByRole('navigation', { name: 'Điều hướng chính' });
    expect(within(nav).getByRole('link', { name: 'Trang chủ' })).toHaveAttribute('href', '/');
    expect(within(nav).getByRole('link', { name: 'HBT Core' })).toHaveAttribute('href', '/core');
    expect(within(nav).getByRole('link', { name: 'PostV' })).toHaveAttribute('href', '/postv');
    expect(within(nav).getByRole('link', { name: 'Chatting' })).toHaveAttribute(
      'href',
      '/chatting',
    );
    expect(within(nav).getByRole('link', { name: 'Cài đặt' })).toHaveAttribute('href', '/settings');

    // Chuyển sang Chế độ V2 và gõ câu nhắc đang dở dang
    const tabV2 = await screen.findByRole('tab', { name: /Chế độ V2 · Tự động 1-Click Prompt/ });
    await user.click(tabV2);
    const promptInput = screen.getByLabelText('Câu nhắc 1-Click Prompt');
    await user.type(promptInput, 'Bí ẩn Kim tự tháp Ai Cập');
    expect(promptInput).toHaveValue('Bí ẩn Kim tự tháp Ai Cập');

    // Chuyển sang phân hệ PostV rồi Chatting rồi quay lại HBT Core
    await user.click(within(nav).getByRole('link', { name: 'PostV' }));
    expect(await screen.findByText('PostV Workspace')).toBeVisible();

    await user.click(within(nav).getByRole('link', { name: 'Chatting' }));
    expect(await screen.findByText('Chatting Workspace')).toBeVisible();

    await user.click(within(nav).getByRole('link', { name: 'HBT Core' }));

    // Kiểm tra trạng thái tab V2 và câu nhắc đang nhập vẫn được giữ nguyên
    expect(
      await screen.findByRole('tab', { name: /Chế độ V2 · Tự động 1-Click Prompt/ }),
    ).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByLabelText('Câu nhắc 1-Click Prompt')).toHaveValue(
      'Bí ẩn Kim tự tháp Ai Cập',
    );
  });
});
