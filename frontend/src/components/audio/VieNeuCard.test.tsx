import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { HbtVoiceInfo } from '../../api/types';
import { ComposePage } from '../../pages/ComposePage';
import { FakeEventSource, json, stubFetch } from '../../test/fakes';
import { project, scene } from '../../test/project';
import { renderWithProviders } from '../../test/render';
import { ToastProvider } from '../Toast';
import { VieNeuCard } from './VieNeuCard';

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal('EventSource', FakeEventSource);
});
afterEach(() => vi.unstubAllGlobals());

const VOICES = {
  default: 'Adam bựa',
  voices: [
    { id: 'Adam bựa', label: 'Adam bựa — Nam', gender: 'Nam', region: 'Bắc', style: '' },
    { id: 'Trúc Ly', label: 'Trúc Ly — Nữ', gender: 'Nữ', region: 'Bắc', style: '' },
  ],
};
const info = (over: Partial<HbtVoiceInfo> = {}): HbtVoiceInfo => ({
  available: true,
  note: null,
  voice_id: null,
  has_file: false,
  file: null,
  url: null,
  from_vieneu: false,
  seconds: null,
  used_voice_id: null,
  stale: null,
  scenes: 3,
  estimated_seconds: 12.5,
  ...over,
});

function open(data: HbtVoiceInfo, extra: Record<string, unknown> = {}) {
  const mock = stubFetch({
    'GET /api/projects/muoi': project({ scenes: [scene(), scene(), scene()] }),
    'PUT /api/projects/muoi': (_u: string, init?: RequestInit) =>
      new Response(String(init?.body), { headers: { 'Content-Type': 'application/json' } }),
    'GET /api/projects/muoi/draft/voice': data,
    'GET /api/voices': VOICES,
    'GET /api/jobs': [],
    'PUT /api/gd2/voice/preferences': { voice_id: 'Trúc Ly' },
    ...extra,
  });
  renderWithProviders(
    <ToastProvider>
      <Routes>
        <Route path="/p/:slug" element={<ComposePage />}>
          <Route index element={<VieNeuCard />} />
        </Route>
      </Routes>
    </ToastProvider>,
    '/p/muoi',
  );
  return mock;
}

const bodiesTo = (mock: ReturnType<typeof stubFetch>, method: string, suffix: string) =>
  mock.mock.calls
    .filter((c) => String(c[0]).endsWith(suffix) && (c[1] as RequestInit)?.method === method)
    .map((c) => (c[1] as RequestInit).body);

describe('VieNeuCard — giọng VieNeu cho HBT', () => {
  it('shows a short note (not hidden) when VieNeu is not installed', async () => {
    open(info({ available: false, note: 'Chưa cài VieNeu (giả)' }));
    const card = await screen.findByRole('region', { name: 'Giọng VieNeu' });
    expect(await screen.findByText('Chưa dùng được VieNeu')).toBeVisible();
    expect(screen.getByText('Chưa cài VieNeu (giả)')).toBeVisible();
    expect(card).toHaveTextContent('thả file giọng (Vbee…)');
    expect(screen.queryByRole('button', { name: 'Tạo giọng' })).not.toBeInTheDocument();
  });

  it('keeps Tạo giọng off with a reminder until a voice is chosen', async () => {
    open(info());
    const btn = await screen.findByRole('button', { name: /^Tạo giọng/ });
    expect(btn).toBeDisabled();
    expect(btn).toHaveTextContent('Chọn giọng trước khi tạo');
  });

  it('remembers the chosen voice on the server and preselects the remembered one', async () => {
    const user = userEvent.setup();
    const mock = open(info());
    const select = await screen.findByLabelText('Giọng đọc');
    await user.selectOptions(select, 'Trúc Ly');
    await waitFor(() =>
      expect(bodiesTo(mock, 'PUT', '/gd2/voice/preferences')).toEqual([
        JSON.stringify({ voice_id: 'Trúc Ly' }),
      ]),
    );
    expect(screen.getByRole('button', { name: 'Tạo giọng' })).toBeEnabled();
  });

  it('starts with the remembered voice, shows scene x/N progress, then the result', async () => {
    const user = userEvent.setup();
    const mock = open(info({ voice_id: 'Adam bựa' }), {
      'POST /api/projects/muoi/draft/voice': () => json({ job_id: 'j1' }, 202),
      'GET /api/jobs/j1': {
        id: 'j1',
        status: 'done',
        output: {
          voice: '/api/files/projects/muoi/voice.wav',
          seconds: 3.9,
          generated: 3,
          cached: 1,
        },
      },
    });
    const select = await screen.findByLabelText('Giọng đọc');
    await waitFor(() => expect(select).toHaveValue('Adam bựa'));
    await user.click(screen.getByRole('button', { name: 'Tạo giọng' }));
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    expect(bodiesTo(mock, 'POST', '/draft/voice')).toEqual([
      JSON.stringify({ voice_id: 'Adam bựa' }),
    ]);
    FakeEventSource.instances[0].emit('progress', {
      progress: 40,
      step: 'voice',
      message: 'Đang đọc cảnh 2/3',
    });
    expect(await screen.findByText('Đang đọc cảnh 2/3')).toBeVisible();
    expect(screen.getByRole('progressbar', { name: 'Tiến độ sinh giọng' })).toHaveAttribute(
      'aria-valuenow',
      '40',
    );
    expect(screen.getByRole('button', { name: 'Huỷ' })).toBeVisible();
    FakeEventSource.instances[0].emit('end', { status: 'done' });
    expect(await screen.findByText('Xong: 3,9 s (đọc mới 3, dùng lại 1)')).toBeVisible();
  });

  it('can cancel a running job and says the old voice is kept', async () => {
    const user = userEvent.setup();
    open(info({ voice_id: 'Adam bựa' }), {
      'POST /api/projects/muoi/draft/voice': () => json({ job_id: 'j2' }, 202),
      'POST /api/jobs/j2/cancel': { id: 'j2', status: 'cancelled' },
      'GET /api/jobs/j2': { id: 'j2', status: 'cancelled', output: null },
    });
    await waitFor(() => expect(screen.getByLabelText('Giọng đọc')).toHaveValue('Adam bựa'));
    await user.click(screen.getByRole('button', { name: 'Tạo giọng' }));
    await user.click(await screen.findByRole('button', { name: 'Huỷ' }));
    FakeEventSource.instances[0].emit('end', { status: 'cancelled' });
    expect(await screen.findByText('Đã huỷ, giọng cũ được giữ nguyên')).toBeVisible();
  });

  it('warns "Sẽ thay giọng hiện có" when a voice file already exists', async () => {
    open(info({ voice_id: 'Adam bựa', has_file: true, file: 'voice.mp3' }));
    expect(await screen.findByText('Sẽ thay giọng hiện có')).toBeVisible();
    expect(await screen.findByRole('button', { name: 'Tạo lại giọng' })).toBeInTheDocument();
  });

  it('tells when the text changed after the voice was made (no auto regenerate)', async () => {
    const mock = open(
      info({
        voice_id: 'Adam bựa',
        has_file: true,
        file: 'voice.wav',
        url: '/api/files/projects/muoi/voice.wav',
        from_vieneu: true,
        seconds: 12.3,
        stale: true,
      }),
    );
    expect(await screen.findByText('Lời đã đổi, tạo lại giọng')).toBeVisible();
    expect(screen.getByLabelText('Nghe giọng VieNeu')).toHaveAttribute(
      'src',
      expect.stringContaining('/api/files/projects/muoi/voice.wav'),
    );
    expect(bodiesTo(mock, 'POST', '/draft/voice')).toEqual([]);
  });

  it('shows nothing about freshness when the state is unknown', async () => {
    open(
      info({
        voice_id: 'Adam bựa',
        has_file: true,
        file: 'voice.wav',
        url: '/api/files/projects/muoi/voice.wav',
        from_vieneu: true,
        stale: null,
      }),
    );
    await screen.findByRole('button', { name: 'Tạo lại giọng' });
    expect(screen.queryByText('Lời đã đổi, tạo lại giọng')).not.toBeInTheDocument();
    expect(screen.queryByText('Giọng khớp lời')).not.toBeInTheDocument();
  });

  it('disables the button when no scene has text', async () => {
    open(info({ voice_id: 'Adam bựa', scenes: 0 }));
    const btn = await screen.findByRole('button', { name: /^Tạo giọng/ });
    expect(btn).toBeDisabled();
    expect(btn).toHaveTextContent('Chưa có cảnh nào có lời đọc');
  });
});
