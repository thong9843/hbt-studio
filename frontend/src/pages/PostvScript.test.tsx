import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider } from '../components/Toast';
import { FakeEventSource, json, stubFetch } from '../test/fakes';
import { renderWithProviders } from '../test/render';
import { PostvLayout } from './PostvLayout';
import { PostvScriptPage } from './PostvScriptPage';

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal('EventSource', FakeEventSource);
});
afterEach(() => vi.unstubAllGlobals());

const stats = { views: null, likes: null, replies: null, reposts: null, shares: null };
const VOICE = { engine: 'vieneu', voice_id: null, file: null, trim_end: null, cast: {}, seed: 1 };

const postv = (over: Record<string, unknown> = {}) => ({
  version: 1,
  kind: 'postv',
  slug: 'bai',
  title: 'Bài đêm khuya',
  series: '',
  source: { url: '', note: '', pasted_at: null },
  post: {
    handle: 'tac_gia',
    age: '17 giờ',
    text: 'Hôm qua mình quên ví.',
    card_text: null,
    ...stats,
  },
  comments: [
    {
      id: 'c1',
      handle: 'user_b',
      age: '14 giờ',
      text: 'Ở đâu vậy',
      parent: null,
      picked: true,
      ...stats,
    },
  ],
  segments: [
    { role: 'hook', card: 'hook', voice: 'Quên ví ở quán', ref: null },
    { role: 'post', card: 'post', voice: 'Hôm qua mình quên ví.', ref: null },
    { role: 'comment', card: 'comment', voice: 'Ở đâu vậy', ref: 'c1' },
    { role: 'commentary', card: 'none', voice: '', ref: null },
  ],
  voice: VOICE,
  music: null,
  ...over,
});

const VOICES = {
  default: 'Adam bựa',
  voices: [
    { id: 'Adam bựa', label: 'Adam bựa — Nam · Bắc', gender: 'Nam', region: 'Bắc', style: '' },
    { id: 'Trúc Ly', label: 'Trúc Ly — Nữ · Bắc', gender: 'Nữ', region: 'Bắc', style: '' },
    { id: 'Mai Anh', label: 'Mai Anh — Nữ · Bắc', gender: 'Nữ', region: 'Bắc', style: '' },
  ],
};

const info = (over: Record<string, unknown> = {}) => ({
  engine: 'vieneu',
  file: null,
  url: null,
  available: true,
  note: null,
  seed: 1,
  manual: {},
  speakers: [
    { speaker: 'narrator', voice_id: 'Adam bựa', manual: false },
    { speaker: 'post', voice_id: 'Trúc Ly', manual: false },
    { speaker: 'c1', voice_id: 'Mai Anh', manual: false },
  ],
  segments: null,
  seconds: null,
  stale: null,
  estimated_seconds: 3.4,
  ...over,
});

function backend(project: unknown, voice: unknown, extra: Record<string, unknown> = {}) {
  const saves: Record<string, unknown>[] = [];
  const mock = stubFetch({
    'GET /api/projects/bai': project,
    'PUT /api/projects/bai': (_u: string, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body));
      saves.push(body);
      return json(body);
    },
    'GET /api/projects/bai/voice': voice,
    'GET /api/voices': VOICES,
    'GET /api/jobs': [],
    'GET /api/music': [],
    ...extra,
  });
  return { saves, mock, last: () => saves[saves.length - 1] as any }; // eslint-disable-line @typescript-eslint/no-explicit-any
}

function app() {
  return renderWithProviders(
    <ToastProvider>
      <Routes>
        <Route path="/postv/:slug" element={<PostvLayout />}>
          <Route path="script" element={<PostvScriptPage />} />
          <Route path="preview" element={<p>bước xem trước</p>} />
          <Route path="pick" element={<p>bước chọn đoạn</p>} />
        </Route>
      </Routes>
    </ToastProvider>,
    '/postv/bai/script',
  );
}

describe('Bước 3 · lời đọc từng đoạn', () => {
  it('lists every segment with its reader, characters and seconds', async () => {
    backend(postv(), info());
    app();
    const list = await screen.findByRole('region', { name: 'Lời đọc từng đoạn' });
    expect(within(list).getAllByRole('textbox')).toHaveLength(4);
    expect(within(list).getAllByText('Người đọc: Người dẫn')).toHaveLength(2); // hook + góc nhìn
    expect(within(list).getByText('Người đọc: tac_gia')).toBeVisible();
    expect(within(list).getByText('Người đọc: user_b')).toBeVisible();
    expect(within(list).getByLabelText('Lời đọc đoạn 4 (Góc nhìn)')).toHaveAttribute(
      'placeholder',
      'Góc nhìn của bạn (tuỳ chọn)',
    );
  });

  it('saves an edited line and goes on to the preview step', async () => {
    const user = userEvent.setup();
    const { last } = backend(postv(), info());
    app();
    const box = await screen.findByLabelText('Lời đọc đoạn 1 (Hook)');
    await user.clear(box);
    await user.type(box, 'Tiêu đề mới');
    await user.click(screen.getByRole('button', { name: 'Tiếp: Xem trước' }));
    expect(await screen.findByText('bước xem trước')).toBeVisible();
    expect(last().segments[0].voice).toBe('Tiêu đề mới');
  });

  it('points back to the pick step when there are no segments', async () => {
    backend(postv({ segments: [] }), info({ speakers: [] }));
    app();
    expect(await screen.findByText('Chưa có đoạn nào. Quay lại bước Chọn đoạn.')).toBeVisible();
    expect(screen.getByRole('link', { name: 'Về bước Chọn đoạn' })).toBeVisible();
  });
});

describe('Thẻ Giọng', () => {
  it('shows who reads with which voice and saves a manual choice', async () => {
    const user = userEvent.setup();
    const { last } = backend(postv(), info());
    app();
    const card = await screen.findByRole('region', { name: 'Giọng đọc' });
    const post = await within(card).findByLabelText('Giọng của tac_gia');
    expect(within(card).getByLabelText('Giọng của Người dẫn')).toHaveDisplayValue(
      'Tự động · Adam bựa — Nam · Bắc',
    );
    await user.selectOptions(post, 'Mai Anh');
    await user.click(screen.getByRole('button', { name: 'Tiếp: Xem trước' }));
    await screen.findByText('bước xem trước');
    expect(last().voice.cast).toEqual({ post: 'Mai Anh' });
  });

  it('goes back to automatic and shuffles with a new seed', async () => {
    const user = userEvent.setup();
    const manual = info({
      manual: { post: 'Mai Anh' },
      speakers: [{ speaker: 'post', voice_id: 'Mai Anh', manual: true }],
    });
    const { last } = backend(postv({ voice: { ...VOICE, cast: { post: 'Mai Anh' } } }), manual);
    app();
    const select = await screen.findByLabelText('Giọng của tac_gia');
    expect(select).toHaveDisplayValue('Mai Anh — Nữ · Bắc');
    await user.selectOptions(select, '');
    await user.click(screen.getByRole('button', { name: 'Đổi giọng' }));
    await user.click(screen.getByRole('button', { name: 'Tiếp: Xem trước' }));
    await screen.findByText('bước xem trước');
    expect(last().voice.cast).toEqual({});
    expect(last().voice.seed).toBe(2);
  });

  it('explains how to install VieNeu and still lets the user import a file', async () => {
    const user = userEvent.setup();
    backend(
      postv(),
      info({ available: false, note: 'Chưa cài VieNeu. Chạy: python -m venv …', speakers: [] }),
    );
    app();
    expect(await screen.findByText('Chưa dùng được VieNeu')).toBeVisible();
    expect(screen.getByText(/Chưa cài VieNeu\. Chạy/)).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Sinh giọng' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Nhập file' }));
    expect(
      screen.getByLabelText('Thả file giọng (mp3, wav, m4a) hoặc bấm để chọn'),
    ).toBeInTheDocument();
  });

  it('keeps Sinh giọng off until some line has text', async () => {
    const empty = postv({
      segments: [{ role: 'hook', card: 'hook', voice: '', ref: null }],
    });
    backend(empty, info({ speakers: [] }));
    app();
    const button = await screen.findByRole('button', { name: /^Sinh giọng/ });
    expect(button).toBeDisabled();
    expect(
      screen.getAllByText('Nhập lời đọc cho ít nhất một đoạn rồi mới sinh giọng.').length,
    ).toBeGreaterThan(0);
  });

  it('runs the synthesis job: progress by segment, then the new voice appears', async () => {
    const user = userEvent.setup();
    let voiceCalls = 0;
    const { mock } = backend(postv(), info(), {
      'GET /api/projects/bai/voice': () => {
        voiceCalls += 1;
        return json(
          voiceCalls === 1
            ? info()
            : info({
                url: '/api/files/projects/bai/voice.wav',
                file: 'voice.wav',
                seconds: 3.9,
                stale: false,
              }),
        );
      },
      'POST /api/projects/bai/voice/synthesize': () => json({ job_id: 'j1' }, 202),
      'GET /api/jobs/j1': {
        id: 'j1',
        project: 'bai',
        status: 'done',
        progress: 100,
        step: 'voice',
        log_tail: [],
        error: null,
        output: {
          voice: '/api/files/projects/bai/voice.wav',
          seconds: 3.9,
          generated: 3,
          cached: 1,
        },
      },
    });
    app();
    await user.click(await screen.findByRole('button', { name: 'Sinh giọng' }));
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    FakeEventSource.instances[0].emit('progress', {
      progress: 40,
      step: 'voice',
      message: 'Đang đọc đoạn 2/4',
    });
    expect(await screen.findByText('Đang đọc đoạn 2/4')).toBeVisible();
    expect(screen.getByRole('progressbar', { name: 'Tiến độ sinh giọng' })).toHaveAttribute(
      'aria-valuenow',
      '40',
    );
    expect(screen.getByRole('button', { name: 'Huỷ' })).toBeVisible();
    FakeEventSource.instances[0].emit('end', { status: 'done' });
    expect(await screen.findByText('Đã sinh xong 3,9 s (3 đoạn mới, 1 dùng lại)')).toBeVisible();
    expect(await screen.findByLabelText('Giọng đã sinh')).toHaveAttribute(
      'src',
      expect.stringContaining('/api/files/projects/bai/voice.wav'),
    );
    expect(screen.getByText('Giọng khớp với lời hiện tại')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Sinh lại giọng' })).toBeVisible();
    expect(mock.mock.calls.filter(([u]) => String(u).endsWith('/voice/synthesize'))).toHaveLength(
      1,
    );
  });

  it('cancels a running job', async () => {
    const user = userEvent.setup();
    const { mock } = backend(postv(), info(), {
      'POST /api/projects/bai/voice/synthesize': () => json({ job_id: 'j2' }, 202),
      'POST /api/jobs/j2/cancel': json({ id: 'j2', status: 'cancelled' }),
      'GET /api/jobs/j2': { id: 'j2', status: 'cancelled', output: null, error: null },
    });
    app();
    await user.click(await screen.findByRole('button', { name: 'Sinh giọng' }));
    await user.click(await screen.findByRole('button', { name: 'Huỷ' }));
    await waitFor(() =>
      expect(mock.mock.calls.some(([u]) => String(u).endsWith('/jobs/j2/cancel'))).toBe(true),
    );
    FakeEventSource.instances[0].emit('end', { status: 'cancelled' });
    expect(await screen.findByText('Đã huỷ sinh giọng')).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Huỷ' })).not.toBeInTheDocument();
  });

  it('shows the error when synthesis fails', async () => {
    const user = userEvent.setup();
    backend(postv(), info(), {
      'POST /api/projects/bai/voice/synthesize': () => json({ job_id: 'j3' }, 202),
      'GET /api/jobs/j3': {
        id: 'j3',
        status: 'failed',
        output: null,
        error: 'VieNeu lỗi lúc nạp mô hình',
      },
    });
    app();
    await user.click(await screen.findByRole('button', { name: 'Sinh giọng' }));
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    FakeEventSource.instances[0].emit('end', { status: 'failed' });
    expect(await screen.findByText('Sinh giọng lỗi: VieNeu lỗi lúc nạp mô hình')).toBeVisible();
  });

  it('reconnects to a voice job that was running before the page reloaded', async () => {
    backend(postv(), info(), {
      'GET /api/jobs': [
        { id: 'j9', slug: 'bai', kind: 'voice', status: 'running', progress: 20, step: 'voice' },
        { id: 'r1', slug: 'bai', kind: 'final', status: 'queued', progress: 0, step: '' },
      ],
    });
    app();
    await waitFor(() =>
      expect(FakeEventSource.instances.map((e) => e.url)).toContain('/api/jobs/j9/events'),
    );
  });

  it('warns that the text changed since the last synthesis', async () => {
    backend(
      postv({ voice: { ...VOICE, file: 'voice.wav' } }),
      info({
        url: '/api/files/projects/bai/voice.wav',
        file: 'voice.wav',
        seconds: 3.9,
        stale: true,
      }),
    );
    app();
    expect(await screen.findByText('Lời đã đổi sau lần sinh trước, hãy sinh lại')).toBeVisible();
    expect(screen.getByText('Dài 3,9 s')).toBeVisible();
  });
});

describe('Thẻ Nhạc', () => {
  it('uses the shared music card on the PostV editor', async () => {
    backend(postv(), info(), { 'GET /api/music': [] });
    app();
    const music = await screen.findByRole('region', { name: 'Nhạc nền' });
    expect(within(music).getByRole('button', { name: 'Không nhạc' })).toBeVisible();
  });

  it('allows removing an attached music file with confirmation', async () => {
    const user = userEvent.setup();
    const deleteMusic = vi.fn(() => new Response(null, { status: 204 }));
    backend(postv({ music: { file: 'music.mp3', credit: 'Sample Artist' } }), info(), {
      'GET /api/music': [],
      'DELETE /api/projects/bai/postv/assets/music': deleteMusic,
    });
    app();
    const musicCard = await screen.findByRole('region', { name: 'Nhạc nền' });
    const removeBtn = within(musicCard).getByRole('button', { name: 'Gỡ file nhạc' });
    await user.click(removeBtn);

    const dialog = await screen.findByRole('alertdialog', { name: 'Gỡ file nhạc' });
    expect(within(dialog).getByText(/Bạn có chắc muốn gỡ file nhạc này\?/)).toBeVisible();

    await user.click(within(dialog).getByRole('button', { name: 'Gỡ file nhạc' }));
    expect(deleteMusic).toHaveBeenCalledTimes(1);
  });
});

describe('Gỡ file giọng đã nạp', () => {
  it('allows removing an uploaded voice file with confirmation', async () => {
    const user = userEvent.setup();
    const deleteVoice = vi.fn(() => new Response(null, { status: 204 }));
    backend(
      postv({ voice: { ...VOICE, engine: 'file', file: 'voice_input.wav' } }),
      info({ engine: 'file', file: 'voice_input.wav' }),
      {
        'DELETE /api/projects/bai/postv/assets/voice': deleteVoice,
      },
    );
    app();
    const voiceCard = await screen.findByRole('region', { name: 'Giọng đọc' });
    const removeBtn = within(voiceCard).getByRole('button', { name: 'Gỡ file giọng' });
    await user.click(removeBtn);

    const dialog = await screen.findByRole('alertdialog', { name: 'Gỡ file giọng' });
    expect(within(dialog).getByText(/Bạn có chắc muốn gỡ file giọng này\?/)).toBeVisible();

    await user.click(within(dialog).getByRole('button', { name: 'Gỡ file giọng' }));
    expect(deleteVoice).toHaveBeenCalledTimes(1);
  });
});
