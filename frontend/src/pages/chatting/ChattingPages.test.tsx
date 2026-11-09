import { screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Route, Routes } from 'react-router-dom';
import { renderWithProviders } from '../../test/render';
import { stubFetch } from '../../test/fakes';
import { ChattingHome } from './ChattingHome';
import { ChattingEditor } from './ChattingEditor';

afterEach(() => vi.unstubAllGlobals());

describe('Chatting Pages (Vitest)', () => {
  it('ChattingHome: hiển thị tiêu đề, ô nhập và các nút chọn', async () => {
    stubFetch({
      'GET /api/chatting/status': {
        ollama_running: true,
        model_available: true,
        model_name: 'qwen2.5:3b-instruct',
        stickers: { soc: 2, cuoi: 1 },
        total_stickers: 3,
      },
      'GET /api/chatting/projects': [
        {
          slug: 'du-an-mau',
          title: 'Dự án chat mẫu',
          platform: 'messenger',
          updated_at: '2026-11-09T09:00:00Z',
          characters_count: 2,
          messages_count: 8,
          has_render: true,
          timings: { llm_s: 1.2 },
        },
      ],
    });

    renderWithProviders(<ChattingHome />, '/chatting');

    expect(await screen.findByText('Chatting')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Dán link Reddit hoặc dán câu chuyện…')).toBeInTheDocument();
    expect(screen.getByText('Messenger')).toBeInTheDocument();
    expect(screen.getByText('Zalo')).toBeInTheDocument();
    expect(screen.getByText('Tạo video')).toBeInTheDocument();
    expect(await screen.findByText('Dự án chat mẫu')).toBeInTheDocument();
  });

  it('ChattingEditor: hiển thị đủ 3 cột biên tập và xem trước', async () => {
    const mockDoc = {
      hbt_chat: 1,
      title: 'Đoạn chat vui',
      platform: 'messenger',
      source: { kind: 'pasted' },
      background: { name: 'minecraft4-1080p60', seed: 7 },
      characters: [
        { id: 'me', name: 'Tôi', side: 'right', voice: 'Adam bựa' },
        { id: 'a', name: 'Linh', side: 'left', voice: 'Trúc Ly' },
      ],
      messages: [
        { from: 'a', text: 'Ngủ chưa bạn?', sticker: null },
        { from: 'me', text: 'Chưa, đang thức nè', sticker: 'cuoi' },
      ],
    };

    stubFetch({
      'GET /api/chatting/test-slug': {
        slug: 'test-slug',
        doc: mockDoc,
        source: { title: 'Đoạn chat vui', body: '...' },
        renders: [],
        preview_url: null,
      },
    });

    renderWithProviders(
      <Routes>
        <Route path="/chatting/:slug" element={<ChattingEditor />} />
      </Routes>,
      '/chatting/test-slug',
    );

    expect(await screen.findByText('Đoạn chat vui')).toBeInTheDocument();
    expect(screen.getByText('Nhân vật')).toBeInTheDocument();
    expect(screen.getByText('Danh sách tin nhắn (2)')).toBeInTheDocument();
    expect(screen.getByText('Xem trước')).toBeInTheDocument();
    expect(screen.getByText('Xem nhanh')).toBeInTheDocument();
    expect(screen.getByText('Xuất bản đẹp')).toBeInTheDocument();
  });

  it('ChattingEditor: hiển thị thông báo cảnh báo cắt tin và bỏ sticker nếu có', async () => {
    const mockDocWithWarnings = {
      hbt_chat: 1,
      title: 'Đoạn chat có cảnh báo',
      platform: 'messenger',
      source: { kind: 'pasted' },
      background: { name: 'minecraft4-1080p60', seed: 7 },
      characters: [
        { id: 'me', name: 'Tôi', side: 'right', voice: 'Adam bựa' },
        { id: 'a', name: 'Linh', side: 'left', voice: 'Trúc Ly' },
      ],
      messages: [
        { from: 'a', text: 'Ngủ chưa bạn?', sticker: null },
        { from: 'me', text: 'Chưa, đang thức nè', sticker: 'cuoi' },
      ],
      warnings: [
        'Đã cắt bớt 2 tin nhắn ở giữa (giữ tin đầu và 2 tin cuối) để kịch bản không vượt quá 900 ký tự.',
        'Đã bỏ 3 sticker dư thừa để đảm bảo tối đa 1 sticker mỗi 3 tin nhắn.',
      ],
    };

    stubFetch({
      'GET /api/chatting/warn-slug': {
        slug: 'warn-slug',
        doc: mockDocWithWarnings,
        source: { title: 'Đoạn chat có cảnh báo', body: '...' },
        renders: [],
        preview_url: null,
      },
    });

    renderWithProviders(
      <Routes>
        <Route path="/chatting/:slug" element={<ChattingEditor />} />
      </Routes>,
      '/chatting/warn-slug',
    );

    expect(await screen.findByText(/Lưu ý kịch bản/)).toBeInTheDocument();
    expect(screen.getByText(/Đã cắt bớt 2 tin nhắn/)).toBeInTheDocument();
    expect(screen.getByText(/Đã bỏ 3 sticker dư thừa/)).toBeInTheDocument();
  });
});
