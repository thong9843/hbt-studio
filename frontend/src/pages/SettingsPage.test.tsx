import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { SensitiveWords } from '../api/types';
import { stubFetch } from '../test/fakes';
import { renderWithProviders } from '../test/render';
import { SettingsPage } from './SettingsPage';

afterEach(() => vi.unstubAllGlobals());

const appSettings = {
  default_fps: 50,
  theme: { primary: '#146268', accent: '#DE5C48' },
  whisper_model: 'auto',
  whisper_timeout_seconds: 300,
};
const words: SensitiveWords = {
  categories: [
    { id: 'alcohol', level: 'warn', words: ['bia', 'rượu'], hint: '' },
    { id: 'drugs', level: 'block', words: ['ma tuý'], hint: '' },
  ],
};

describe('Settings page: sensitive words', () => {
  it('explains the matching rules and saves the edited list', async () => {
    const saved: SensitiveWords[] = [];
    stubFetch({
      'GET /api/settings/app': appSettings,
      'GET /api/settings/sensitive-words': words,
      'PUT /api/settings/sensitive-words': (_url: string, init?: RequestInit) => {
        const body = JSON.parse(String(init?.body)) as SensitiveWords;
        saved.push(body);
        return new Response(JSON.stringify(body), {
          headers: { 'Content-Type': 'application/json' },
        });
      },
    });
    const user = userEvent.setup();
    renderWithProviders(<SettingsPage />);

    expect(await screen.findByText(/"bia" khác "bìa"/)).toBeInTheDocument();
    expect(screen.queryByText(/Kiểm tra từ khoá sẽ bật/)).toBeNull();

    const lists = await screen.findAllByLabelText('Danh sách từ');
    await user.type(lists[0], '{Enter}nhậu');
    await user.click(screen.getByRole('button', { name: 'Lưu danh sách' }));

    await waitFor(() => expect(saved).toHaveLength(1));
    expect(saved[0].categories[0].words).toEqual(['bia', 'rượu', 'nhậu']);
    expect(saved[0].categories[1]).toMatchObject({ id: 'drugs', level: 'block' });
    expect(await screen.findByText('Đã lưu danh sách')).toBeInTheDocument();
  });
});

describe('Settings page: Whisper note', () => {
  const open = (health: Record<string, unknown> | undefined) => {
    stubFetch({
      'GET /api/settings/app': appSettings,
      'GET /api/settings/sensitive-words': words,
      ...(health ? { 'GET /api/health': health } : {}),
    });
    renderWithProviders(<SettingsPage />);
  };
  const base = { ok: true, ffmpeg: true, missing: [] };

  it('explains the GPU path when the machine has a GPU', async () => {
    open({ ...base, whisper: true, gpu: true });
    expect(await screen.findByText(/có GPU.*large-v3 trên GPU/)).toBeInTheDocument();
  });

  it('explains the CPU path when there is no GPU', async () => {
    open({ ...base, whisper: true, gpu: false });
    expect(await screen.findByText(/không có GPU.*small trên CPU/)).toBeInTheDocument();
  });

  it('says Whisper is not installed and silence alignment is used', async () => {
    open({ ...base, whisper: false, gpu: false });
    expect(await screen.findByText(/Chưa cài faster-whisper/)).toBeInTheDocument();
  });

  it('shows the generic note while the health check is not available', async () => {
    open(undefined);
    expect(
      await screen.findByText(/căn theo khoảng lặng\. Phương pháp đã dùng/),
    ).toBeInTheDocument();
  });
});
