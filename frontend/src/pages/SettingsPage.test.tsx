import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { AppSettings, SensitiveWords } from '../api/types';
import { stubFetch } from '../test/fakes';
import { renderWithProviders } from '../test/render';
import { SettingsPage } from './SettingsPage';

afterEach(() => vi.unstubAllGlobals());

const appSettings: AppSettings = {
  default_fps: 50,
  theme: { primary: '#146268', accent: '#DE5C48' },
  whisper_model: 'auto',
  whisper_timeout_seconds: 300,
};
const words: SensitiveWords = {
  categories: [
    { id: 'alcohol', level: 'warn', words: ['bia', 'rượu'], hint: '' },
    { id: 'drugs', level: 'block', words: ['ma tuý'], hint: '' },
    { id: 'misc', level: 'info', words: ['thuốc'], hint: '' },
  ],
};
const json = (body: unknown) =>
  new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } });

function open(health?: Record<string, unknown>) {
  const savedApp: AppSettings[] = [];
  const savedWords: SensitiveWords[] = [];
  stubFetch({
    'GET /api/settings/app': appSettings,
    'GET /api/settings/sensitive-words': words,
    'PUT /api/settings/app': (_u: string, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body)) as AppSettings;
      savedApp.push(body);
      return json(body);
    },
    'PUT /api/settings/sensitive-words': (_u: string, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body)) as SensitiveWords;
      savedWords.push(body);
      return json(body);
    },
    ...(health ? { 'GET /api/health': health } : {}),
  });
  renderWithProviders(<SettingsPage />);
  return { savedApp, savedWords };
}
const base = { ok: true, ffmpeg: true, missing: [] };

describe('Cài đặt: các thẻ', () => {
  it('shows the four cards with the saved values selected', async () => {
    open();
    expect(await screen.findByRole('heading', { name: 'Cài đặt' })).toBeInTheDocument();
    expect(await screen.findByRole('region', { name: 'FPS mặc định' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Căn chữ' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Màu chủ đề' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Từ nhạy cảm' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '50 fps' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Tự động' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('saves nothing until Lưu, then sends both settings and the word list', async () => {
    const { savedApp, savedWords } = open();
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: '60 fps' }));
    await user.click(screen.getByRole('button', { name: 'small' }));
    expect(screen.getByText('Chưa lưu')).toBeInTheDocument();
    expect(savedApp).toHaveLength(0);

    await user.click(screen.getByRole('button', { name: 'Lưu' }));
    await waitFor(() => expect(savedApp).toHaveLength(1));
    expect(savedApp[0]).toMatchObject({ default_fps: 60, whisper_model: 'small' });
    expect(savedWords).toHaveLength(1);
    expect(await screen.findByText('Đã lưu')).toBeInTheDocument();
  });

  it('warns that medium / large-v3 are slow without a GPU', async () => {
    open();
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'large-v3' }));
    expect(screen.getByRole('note')).toHaveTextContent(/chạy chậm/);
  });

  it('blocks Lưu while a colour is not #RRGGBB', async () => {
    open();
    const user = userEvent.setup();
    const hex = await screen.findByLabelText('Màu chủ đạo mặc định (#RRGGBB)');
    await user.clear(hex);
    await user.type(hex, '#12');
    expect(screen.getByRole('button', { name: /^Lưu( \(.*\))?$/ })).toBeDisabled();
    expect(screen.getAllByText('Màu cần dạng #RRGGBB.').length).toBeGreaterThan(0);
  });
});

describe('Cài đặt: từ nhạy cảm', () => {
  it('shows words as chips, adds one with Enter and removes one with ×', async () => {
    const { savedWords } = open();
    const user = userEvent.setup();
    const list = await screen.findByRole('list', { name: 'Từ của nhóm alcohol' });
    expect(within(list).getByRole('button', { name: 'Bỏ từ bia' })).toBeInTheDocument();

    const inputs = screen.getAllByLabelText('Thêm từ');
    await user.type(inputs[0], 'nhậu{Enter}');
    await user.click(within(list).getByRole('button', { name: 'Bỏ từ bia' }));
    await user.click(screen.getByRole('button', { name: 'Lưu' }));

    await waitFor(() => expect(savedWords).toHaveLength(1));
    expect(savedWords[0].categories[0].words).toEqual(['rượu', 'nhậu']);
    expect(savedWords[0].categories[1]).toMatchObject({ id: 'drugs', level: 'block' });
  });

  it('switches a group between Lưu ý / Cảnh báo / Chặn', async () => {
    const { savedWords } = open();
    const user = userEvent.setup();
    const group = (await screen.findByRole('list', { name: 'Từ của nhóm alcohol' })).closest('li')!;
    await user.click(within(group).getByRole('button', { name: 'Chặn' }));
    await user.click(screen.getByRole('button', { name: 'Lưu' }));
    await waitFor(() => expect(savedWords).toHaveLength(1));
    expect(savedWords[0].categories[0].level).toBe('block');
  });

  it('folds the rarely used (Lưu ý) groups into a collapsed section', async () => {
    open();
    const user = userEvent.setup();
    await screen.findByRole('list', { name: 'Từ của nhóm alcohol' });
    expect(screen.queryByRole('list', { name: 'Từ của nhóm misc' })).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Nhóm ít dùng (1)' }));
    expect(screen.getByRole('list', { name: 'Từ của nhóm misc' })).toBeInTheDocument();
  });

  it('adds and removes a whole group', async () => {
    const { savedWords } = open();
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: '+ Thêm nhóm' }));
    const drugs = (await screen.findByRole('list', { name: 'Từ của nhóm drugs' })).closest('li')!;
    await user.click(within(drugs).getByRole('button', { name: 'Bỏ nhóm' }));
    await user.click(screen.getByRole('button', { name: 'Lưu' }));
    await waitFor(() => expect(savedWords).toHaveLength(1));
    expect(savedWords[0].categories.map((c) => c.id)).toEqual(['alcohol', 'misc', 'nhom_4']);
  });
});

describe('Cài đặt: ghi chú Whisper', () => {
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
