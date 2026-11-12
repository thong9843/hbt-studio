import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { HbtCoreStudioDialog } from './HbtCoreStudioDialog';
import { ToastProvider } from '../Toast';
import { FakeEventSource, stubFetch } from '../../test/fakes';
import { renderWithProviders } from '../../test/render';

afterEach(() => vi.unstubAllGlobals());

const geminiModelsMock = {
  models: [
    { id: 'gemini-3.8-flash', name: 'Gemini 3.8 Flash (Mặc định / Nhanh)' },
    { id: 'gemini-3.6-flash', name: 'Gemini 3.6 Flash' },
    { id: 'gemini-3.5-flash-lite', name: 'Gemini 3.5 Flash Lite (Nhẹ / Tiết kiệm)' },
    { id: 'gemini-3.1-flash-lite', name: 'Gemini 3.1 Flash Lite' },
  ],
  default: 'gemini-3.8-flash',
};

const assetsMock = {
  topics: ['history', 'fun', 'science', 'mystery'],
  sfx: [
    { id: 'fast-swoosh', name: 'universfield-fast-swoosh-383967.mp3', category: 'whoosh' },
    { id: 'pop', name: 'dragon-studio-pop-402324.mp3', category: 'pop' },
  ],
  sfx_presets: ['whoosh', 'pop', 'impact', 'none'],
  topic_music: {
    history: ['alex-morgan-drama-slow-burn-confession-578478.mp3'],
    fun: ['echoes_of_lumen-quirky-music-584892.mp3'],
    science: ['kulakovka-lo-fi-chill-620585.mp3'],
    mystery: ['leberch-quirky-sneaky-375264.mp3'],
  },
  images: ['images/scene-01.png', 'images/scene-02.png'],
  gemini_configured: true,
};

function renderDialog() {
  return renderWithProviders(
    <ToastProvider>
      <Routes>
        <Route path="/" element={<HbtCoreStudioDialog open onClose={() => {}} />} />
        <Route path="/p/:slug" element={<p>Trang dự án</p>} />
      </Routes>
    </ToastProvider>,
  );
}

describe('HbtCoreStudioDialog (V1 & V2)', () => {
  it('renders V1 manual JSON mode by default and triggers 0-token offline render pipeline', async () => {
    FakeEventSource.instances = [];
    vi.stubGlobal('EventSource', FakeEventSource);

    let postedBody: Record<string, unknown> | null = null;
    stubFetch({
      'GET /api/hbt-core/assets': assetsMock,
      'POST /api/hbt-core/v1/render': (_url: string, init?: RequestInit) => {
        postedBody = JSON.parse(String(init?.body)) as Record<string, unknown>;
        return new Response(
          JSON.stringify({
            ok: true,
            mode: 'v1',
            slug: 'dau-truong-la-ma',
            job_id: 'job-v1-123',
            script: postedBody.script,
          }),
          { status: 202, headers: { 'Content-Type': 'application/json' } },
        );
      },
    });

    const user = userEvent.setup();
    renderDialog();

    expect(await screen.findByRole('tab', { name: /Chế độ V1 · Bán tự động/ })).toHaveAttribute(
      'aria-selected',
      'true',
    );

    // Chỉnh sửa trực tiếp lời thoại phân đoạn 1
    const seg1Input = screen.getByLabelText('Lời thoại phân đoạn 1');
    await user.clear(seg1Input);
    await user.type(seg1Input, 'Lời thoại mới đã chỉnh sửa ở chế độ V1.');

    // Bấm "Dựng video"
    await user.click(screen.getByRole('button', { name: 'Dựng video' }));

    await waitFor(() => expect(postedBody).not.toBeNull());
    expect(FakeEventSource.instances).toHaveLength(1);
  });

  it('automatically switches from V2 to V1 mode with a clear alert when Gemini API fails or quota is exceeded', async () => {
    stubFetch({
      'GET /api/hbt-core/assets': assetsMock,
      'POST /api/hbt-core/v2/prompt': () =>
        new Response(
          JSON.stringify({
            detail:
              'Gemini API đã hết hạn mức (Quota 429). Đã tự động chuyển sang Chế độ V1 (Bán tự động / JSON Thủ công).',
            reason: 'quota_exceeded',
            fallback_v1: true,
          }),
          { status: 429, headers: { 'Content-Type': 'application/json' } },
        ),
    });

    const user = userEvent.setup();
    renderDialog();

    // Chuyển sang Tab V2
    const tabV2 = await screen.findByRole('tab', { name: /Chế độ V2 · Tự động 1-Click Prompt/ });
    await user.click(tabV2);
    expect(tabV2).toHaveAttribute('aria-selected', 'true');

    // Nhập prompt và bấm 1-Click
    const promptBox = screen.getByLabelText('Câu nhắc 1-Click Prompt');
    await user.type(promptBox, 'Làm video vì sao về Đấu trường La Mã');
    await user.click(screen.getByRole('button', { name: 'Tạo kịch bản & Dựng video (1-Click)' }));

    // Kiểm tra thông báo lỗi rõ ràng và tự động chuyển về Tab V1
    expect(
      await screen.findByText('Đã tự động chuyển sang Chế độ V1 (Phao cứu sinh)'),
    ).toBeVisible();
    expect(screen.getByRole('tab', { name: /Chế độ V1 · Bán tự động/ })).toHaveAttribute(
      'aria-selected',
      'true',
    );
  });

  it('allows selecting a Gemini model in V2 mode and sends selectedModel in API payload', async () => {
    const capturedBodies: Record<string, unknown>[] = [];
    stubFetch({
      'GET /api/hbt-core/assets': assetsMock,
      'GET /api/hbt/core/models': geminiModelsMock,
      'POST /api/hbt-core/v2/prompt': (_url: string, init?: RequestInit) => {
        capturedBodies.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
        return new Response(
          JSON.stringify({
            ok: true,
            mode: 'v2',
            slug: 'dau-truong-la-ma',
            job_id: null,
            script: {
              title: 'Vì sao Đấu trường La Mã vĩ đại?',
              topic: 'history',
              segments: [
                {
                  order: 1,
                  text: 'Đấu trường La Mã là kỳ quan cổ đại.',
                  image: 'scene-01.png',
                  sfx: 'whoosh',
                },
              ],
            },
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      },
    });

    const user = userEvent.setup();
    renderDialog();

    const tabV2 = await screen.findByRole('tab', { name: /Chế độ V2 · Tự động 1-Click Prompt/ });
    await user.click(tabV2);

    const modelSelect = screen.getByLabelText('Mô hình Gemini (Model)') as HTMLSelectElement;
    expect(modelSelect.value).toBe('gemini-3.8-flash');
    await user.selectOptions(modelSelect, 'gemini-3.5-flash-lite');
    expect(modelSelect.value).toBe('gemini-3.5-flash-lite');

    await user.type(
      screen.getByLabelText('Câu nhắc 1-Click Prompt'),
      'Làm video vì sao về Đấu trường La Mã',
    );
    await user.click(screen.getByRole('button', { name: 'Tạo kịch bản & Dựng video (1-Click)' }));

    await waitFor(() => expect(capturedBodies).toHaveLength(1));
    expect(capturedBodies[0]?.selectedModel).toBe('gemini-3.5-flash-lite');
  });

  it('automatically switches from V2 to V1 mode when backend returns structured fallback JSON (200 OK with success=false, fallback_v1=true)', async () => {
    stubFetch({
      'GET /api/hbt-core/assets': assetsMock,
      'POST /api/hbt-core/v2/prompt': () =>
        new Response(
          JSON.stringify({
            success: false,
            fallback_v1: true,
            error: 'RuntimeError: Unexpected error',
            message:
              'Hệ thống gặp sự cố khi tạo kịch bản tự động V2. Đã tự động chuyển sang Chế độ V1 (Phao cứu sinh).',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
    });

    const user = userEvent.setup();
    renderDialog();

    const tabV2 = await screen.findByRole('tab', { name: /Chế độ V2 · Tự động 1-Click Prompt/ });
    await user.click(tabV2);

    const promptBox = screen.getByLabelText('Câu nhắc 1-Click Prompt');
    await user.type(promptBox, 'Làm video vì sao về Đấu trường La Mã');
    await user.click(screen.getByRole('button', { name: 'Tạo kịch bản & Dựng video (1-Click)' }));

    expect(
      await screen.findByText('Đã tự động chuyển sang Chế độ V1 (Phao cứu sinh)'),
    ).toBeVisible();
    expect(
      screen.getAllByText(/Hệ thống gặp sự cố khi tạo kịch bản tự động V2/).length,
    ).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole('tab', { name: /Chế độ V1 · Bán tự động/ })).toHaveAttribute(
      'aria-selected',
      'true',
    );
  });
});
