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

describe('HbtCoreWorkspace (Prompt-First & V1/V2)', () => {
  it('renders Prompt-first bar + Live 9:16 preview and triggers V1 offline render pipeline', async () => {
    FakeEventSource.instances = [];
    vi.stubGlobal('EventSource', FakeEventSource);

    let postedBody: Record<string, unknown> | null = null;
    stubFetch({
      'GET /api/hbt-core/assets': assetsMock,
      'GET /api/hbt/core/models': geminiModelsMock,
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

    expect(await screen.findByLabelText('Câu nhắc 1-Click Prompt')).toBeVisible();
    expect(screen.getByRole('region', { name: 'Xem trước trực tiếp 9:16' })).toBeVisible();

    // Chỉnh sửa trực tiếp lời thoại phân đoạn 1
    const seg1Input = screen.getByLabelText('Lời thoại phân đoạn 1');
    await user.clear(seg1Input);
    await user.type(seg1Input, 'Lời thoại mới đã chỉnh sửa.');

    // Bấm "Dựng video"
    await user.click(screen.getByRole('button', { name: 'Dựng video' }));

    await waitFor(() => expect(postedBody).not.toBeNull());
    expect(FakeEventSource.instances).toHaveLength(1);
  });

  it('reveals hidden JSON editor via advanced toggle and parses Hay Biet Tot schema without 750-word warnings', async () => {
    stubFetch({
      'GET /api/hbt-core/assets': assetsMock,
      'GET /api/hbt/core/models': geminiModelsMock,
    });

    const user = userEvent.setup();
    renderDialog();

    // Khung JSON được giấu mặc định
    expect(screen.queryByLabelText(/Khối JSON kịch bản/)).toBeNull();

    // Mở menu Vi chỉnh nâng cao (JSON)
    await user.click(screen.getByRole('button', { name: 'Vi chỉnh nâng cao (JSON)' }));

    const longSpeech = Array.from({ length: 800 }, () => 'từ').join(' ');
    const hbtJson = JSON.stringify({
      topic: 'Bí ẩn đại dương',
      total_segments: 1,
      segments: [
        {
          id: 1,
          title: 'KHÁM PHÁ ĐÁY BIỂN',
          text: longSpeech,
          sticker: 'shock',
          image_prompt: 'Deep ocean bioluminescence cinematic shot, 9:16 vertical framing',
        },
      ],
    });

    const textarea = await screen.findByLabelText(/Khối JSON kịch bản/);
    await user.clear(textarea);
    await user.click(textarea);
    await user.paste(hbtJson);
    await user.click(screen.getByRole('button', { name: 'Nạp JSON xuống dòng chỉnh sửa' }));

    expect(await screen.findByDisplayValue('KHÁM PHÁ ĐÁY BIỂN')).toBeInTheDocument();
    expect(
      screen.getByDisplayValue('Deep ocean bioluminescence cinematic shot, 9:16 vertical framing'),
    ).toBeInTheDocument();
    expect(screen.queryByText(/750/)).not.toBeInTheDocument();
  });

  it('opens advanced JSON fallback notice when Gemini API fails or quota is exceeded', async () => {
    stubFetch({
      'GET /api/hbt-core/assets': assetsMock,
      'GET /api/hbt/core/models': geminiModelsMock,
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

    const promptBox = await screen.findByLabelText('Câu nhắc 1-Click Prompt');
    await user.type(promptBox, 'Làm video vì sao về Đấu trường La Mã');
    await user.click(screen.getByRole('button', { name: 'Tạo & Dựng video' }));

    expect(
      await screen.findByText('Đã tự động chuyển sang Chế độ V1 (Phao cứu sinh)'),
    ).toBeVisible();
    expect(await screen.findByLabelText(/Khối JSON kịch bản/)).toBeVisible();
  });

  it('allows selecting a Gemini model in the prompt toolbar and sends selectedModel in API payload', async () => {
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

    const modelSelect = (await screen.findByLabelText(
      'Mô hình Gemini (Model)',
    )) as HTMLSelectElement;
    expect(modelSelect.value).toBe('gemini-3.8-flash');
    await user.selectOptions(modelSelect, 'gemini-3.5-flash-lite');
    expect(modelSelect.value).toBe('gemini-3.5-flash-lite');

    await user.type(
      screen.getByLabelText('Câu nhắc 1-Click Prompt'),
      'Làm video vì sao về Đấu trường La Mã',
    );
    await user.click(screen.getByRole('button', { name: 'Tạo & Dựng video' }));

    await waitFor(() => expect(capturedBodies).toHaveLength(1));
    expect(capturedBodies[0]?.selectedModel).toBe('gemini-3.5-flash-lite');
  });
});
