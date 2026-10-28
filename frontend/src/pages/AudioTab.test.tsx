import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { MusicEntry, Project, RenderRecord } from '../api/types';
import { stubFetch } from '../test/fakes';
import { project } from '../test/project';
import { renderWithProviders } from '../test/render';
import { AudioTab } from './AudioTab';
import { ComposePage } from './ComposePage';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const json = (body: unknown) =>
  new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } });
const png = () => new Response(new Blob(['png'], { type: 'image/png' }));

const track = (over: Partial<MusicEntry> = {}): MusicEntry => ({
  id: 'wacky',
  file: 'funny/wacky.mp3',
  title: 'The Wacky Sprint',
  artist: 'nkbloom',
  source: 'Pixabay',
  url: '',
  license: 'Pixabay Content License',
  moods: ['vui'],
  bpm: null,
  ...over,
});

const render = (over: Partial<RenderRecord> = {}): RenderRecord => ({
  job_id: 'j1',
  preview: true,
  fps: 30,
  duration: 20,
  created_at: '2026-10-23T10:00:00Z',
  video: '/api/files/v.mp4',
  width: 540,
  height: 960,
  lufs: -14,
  aligner: 'silence',
  music_start: 12,
  music_start_source: 'auto',
  music_matches_current: true,
  preview_seconds: null,
  size: 1,
  srt: null,
  publish: null,
  log: null,
  cover: null,
  youtube_cover: null,
  ...over,
});

const MUSIC = { file: 'music.mp3', start: null, credit: 'The Wacky Sprint – nkbloom (Pixabay)' };

interface Setup {
  proj?: Project;
  renders?: RenderRecord[];
  library?: MusicEntry[];
  extra?: Record<string, unknown>;
}

function open({ proj = project(), renders = [], library = [], extra = {} }: Setup = {}) {
  const saved: Project[] = [];
  const mock = stubFetch({
    'GET /api/projects/muoi': proj,
    'PUT /api/projects/muoi': (_u: string, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body)) as Project;
      saved.push(body);
      return json(body);
    },
    'GET /api/music': library,
    'GET /api/projects/muoi/renders': renders,
    'POST /api/projects/muoi/scenes/0/preview.png': png,
    'POST /api/projects/muoi/scenes/1/preview.png': png,
    'POST /api/projects/muoi/scenes/2/preview.png': png,
    ...extra,
  });
  renderWithProviders(
    <Routes>
      <Route path="/p/:slug" element={<ComposePage />}>
        <Route path="audio" element={<AudioTab />} />
        <Route path="export" element={<p>export-tab</p>} />
      </Route>
    </Routes>,
    '/p/muoi/audio',
  );
  return { saved, mock };
}

const lastSaved = (saved: Project[]) => saved.at(-1);

describe('Âm thanh: bố cục', () => {
  it('shows the three cards and the shared 9:16 preview pane with n/N', async () => {
    open();
    expect(await screen.findByRole('heading', { name: 'Giọng đọc' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Điểm bắt đầu nhạc' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Nhạc nền' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Xem nhanh/ })).toBeInTheDocument();
    const user = userEvent.setup();
    expect(screen.getByText('1/3')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Cảnh sau' }));
    expect(screen.getByText('2/3')).toBeInTheDocument();
  });

  it('Xem nhanh only switches to the export tab', async () => {
    const proj = project({
      voice: 'voice.mp3',
      scenes: project().scenes.map((s) => ({ ...s, image: 'images/a.png' })),
    });
    const { mock } = open({ proj });
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: /^Xem nhanh/ }));
    expect(await screen.findByText('export-tab')).toBeInTheDocument();
    expect(
      mock.mock.calls.some(
        ([url, init]) =>
          (init as RequestInit)?.method === 'POST' && String(url).endsWith('/projects/muoi/render'),
      ),
    ).toBe(false);
  });

  it('puts the preview in a drawer below 1024 px', async () => {
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: false,
      media: query,
      addEventListener() {},
      removeEventListener() {},
    }));
    open();
    await screen.findByRole('heading', { name: 'Giọng đọc' });
    expect(screen.queryByRole('button', { name: /^Xem nhanh/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Xem trước' }));
    expect(await screen.findByRole('button', { name: /^Xem nhanh/ })).toBeInTheDocument();
  });

  it('loads the render history once and never polls', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { mock } = open({ renders: [render()] });
    await screen.findByRole('heading', { name: 'Giọng đọc' });
    const count = () => mock.mock.calls.filter(([u]) => String(u).endsWith('/renders')).length;
    await waitFor(() => expect(count()).toBe(1));
    await vi.advanceTimersByTimeAsync(5 * 60_000);
    expect(count()).toBe(1);
  });
});

describe('Âm thanh: giọng đọc', () => {
  it('shows the trimmed tail of the latest render with a Nghe button', async () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
    open({
      proj: project({ voice: 'voice.mp3' }),
      renders: [render({ trimmed_tail: '/api/files/projects/muoi/renders/j1/trimmed_tail.wav' })],
    });
    const user = userEvent.setup();
    expect(await screen.findByText('Đã cắt đuôi')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Nghe phần đã cắt' }));
    expect(play).toHaveBeenCalled();
    const audio = document.querySelector('audio[src$="trimmed_tail.wav"]');
    expect(audio).not.toBeNull();
  });

  it('hides the trimmed tail when there is no render or nothing was cut', async () => {
    open({ proj: project({ voice: 'voice.mp3' }), renders: [render({ trimmed_tail: null })] });
    await screen.findByRole('heading', { name: 'Giọng đọc' });
    await waitFor(() => expect(screen.queryByText('Đã cắt đuôi')).not.toBeInTheDocument());
  });

  it('saves a hand trim point and removes it again', async () => {
    const { saved } = open({ proj: project({ voice: 'voice.mp3' }) });
    const user = userEvent.setup();
    const input = await screen.findByLabelText('Cắt đuôi tại giây');
    await user.type(input, '41.5');
    await waitFor(
      () => expect(lastSaved(saved)?.voice).toEqual({ file: 'voice.mp3', trim_end: 41.5 }),
      {
        timeout: 3000,
      },
    );
    await user.clear(input);
    await waitFor(() => expect(lastSaved(saved)?.voice).toBe('voice.mp3'), { timeout: 3000 });
  });

  it('uploads a dropped voice file as kind=voice', async () => {
    let form: FormData | undefined;
    open({
      extra: {
        'POST /api/projects/muoi/assets': (_u: string, init?: RequestInit) => {
          form = init?.body as FormData;
          return json({
            kind: 'voice',
            path: 'voice.mp3',
            project: project({ voice: 'voice.mp3' }),
          });
        },
      },
    });
    const input = await screen.findByLabelText(/Thả file giọng/);
    await userEvent.upload(input, new File(['x'], 'v.mp3', { type: 'audio/mpeg' }));
    await waitFor(() => expect(form).toBeDefined());
    expect(form?.get('kind')).toBe('voice');
    expect(await screen.findByLabelText('Cắt đuôi tại giây')).toBeInTheDocument();
  });
});

describe('Âm thanh: điểm bắt đầu nhạc', () => {
  const withMusic = (start: number | null = null) => project({ music: { ...MUSIC, start } });

  it('asks for music first when none is chosen', async () => {
    open();
    expect(await screen.findByText('Chọn nhạc nền để đặt điểm bắt đầu.')).toBeInTheDocument();
  });

  it('Tự chọn ↔ Đặt tay: types seconds, saves them, and goes back to automatic', async () => {
    const { saved } = open({ proj: withMusic() });
    const user = userEvent.setup();
    const auto = await screen.findByRole('button', { name: 'Tự chọn' });
    expect(auto).toHaveAttribute('aria-pressed', 'true');
    await user.click(screen.getByRole('button', { name: 'Đặt tay' }));
    const input = await screen.findByLabelText('Bắt đầu nhạc tại giây');
    await user.clear(input);
    await user.type(input, '7');
    await waitFor(() => expect(lastSaved(saved)?.music?.start).toBe(7), { timeout: 3000 });
    await user.click(screen.getByRole('button', { name: 'Tự chọn' }));
    await waitFor(() => expect(lastSaved(saved)?.music?.start).toBeNull(), { timeout: 3000 });
    expect(screen.queryByLabelText('Bắt đầu nhạc tại giây')).not.toBeInTheDocument();
  });

  it('shows "Lần trước: giây X" and Dùng switches to Đặt tay with that second', async () => {
    const { saved } = open({ proj: withMusic(), renders: [render()] });
    const user = userEvent.setup();
    expect(await screen.findByText('Lần trước: giây 12')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Dùng' }));
    expect(screen.getByRole('button', { name: 'Đặt tay' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByLabelText('Bắt đầu nhạc tại giây')).toHaveValue(12);
    await waitFor(() => expect(lastSaved(saved)?.music?.start).toBe(12), { timeout: 3000 });
    expect(screen.queryByRole('button', { name: 'Dùng' })).not.toBeInTheDocument();
  });

  it('hides the line when there is no render, the music changed, or the second was set by hand', async () => {
    for (const renders of [
      [],
      [render({ music_matches_current: false })],
      [render({ music_start: 3, music_start_source: 'manual' })],
    ]) {
      const view = open({ proj: withMusic(), renders });
      await screen.findByRole('button', { name: 'Tự chọn' });
      await waitFor(() => expect(screen.queryByText(/Lần trước/)).not.toBeInTheDocument());
      expect(screen.queryByRole('button', { name: 'Dùng' })).not.toBeInTheDocument();
      void view;
      document.body.innerHTML = '';
    }
  });

  it('plays the 10 s preview from the chosen second', async () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
    open({ proj: withMusic(5) });
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Nghe thử 10 giây' }));
    expect(play).toHaveBeenCalled();
    const audio = document.querySelector('audio[src="/api/files/projects/muoi/music.mp3"]');
    expect((audio as HTMLAudioElement).currentTime).toBe(5);
  });

  it('plays the last automatic second when listening to "Lần trước"', async () => {
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
    open({ proj: withMusic(), renders: [render()] });
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Nghe đoạn lần trước' }));
    const audio = document.querySelector('audio[src="/api/files/projects/muoi/music.mp3"]');
    expect((audio as HTMLAudioElement).currentTime).toBe(12);
  });
});

describe('Âm thanh: nhạc nền', () => {
  const lib = [
    track(),
    track({ id: 'calm', title: 'Calm Lake', artist: 'ava', moods: ['êm', 'thư giãn'] }),
    track({ id: 'none', title: 'No Mood', artist: 'zed', moods: [] }),
  ];

  it('lists tracks with artist · source and mood badges, and filters by mood', async () => {
    open({ library: lib });
    const user = userEvent.setup();
    const group = await screen.findByRole('group', { name: 'Lọc theo tâm trạng' });
    expect(
      within(group)
        .getAllByRole('button')
        .map((b) => b.textContent),
    ).toEqual(['Tất cả', 'êm', 'thư giãn', 'vui']);
    expect(screen.getByText('nkbloom · Pixabay')).toBeInTheDocument();
    await user.click(within(group).getByRole('button', { name: 'êm' }));
    expect(screen.getByText('Calm Lake')).toBeInTheDocument();
    expect(screen.queryByText('The Wacky Sprint')).not.toBeInTheDocument();
    expect(screen.queryByText('No Mood')).not.toBeInTheDocument();
    await user.click(within(group).getByRole('button', { name: 'Tất cả' }));
    expect(screen.getByText('No Mood')).toBeInTheDocument();
  });

  it('hides the mood filter and badges when no track has a mood', async () => {
    open({ library: [track({ moods: [] })] });
    await screen.findByText('The Wacky Sprint');
    expect(screen.queryByRole('group', { name: 'Lọc theo tâm trạng' })).not.toBeInTheDocument();
  });

  it('explains an empty library', async () => {
    open({ library: [] });
    expect(await screen.findByText(/Thư viện chưa có bài nào/)).toBeInTheDocument();
  });

  it('chooses a track from the library and marks it "Đang dùng"', async () => {
    let attached: unknown;
    open({
      library: lib,
      extra: {
        'POST /api/projects/muoi/music/from-library': (_u: string, init?: RequestInit) => {
          attached = JSON.parse(String(init?.body));
          return json(
            project({
              music: { file: 'music.mp3', start: null, credit: 'Calm Lake – ava (Pixabay)' },
            }),
          );
        },
      },
    });
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Chọn Calm Lake' }));
    await waitFor(() => expect(attached).toEqual({ id: 'calm' }));
    const row = (await screen.findByText('Calm Lake')).closest('li') as HTMLElement;
    await waitFor(() => expect(within(row).getByText('Đang dùng')).toBeInTheDocument());
    expect(within(row).queryByRole('button', { name: /^Chọn/ })).not.toBeInTheDocument();
  });

  it('marks the track matching the project credit as in use', async () => {
    open({ proj: project({ music: MUSIC }), library: lib });
    const row = (await screen.findByText('The Wacky Sprint')).closest('li') as HTMLElement;
    expect(within(row).getByText('Đang dùng')).toBeInTheDocument();
    expect(row).toHaveAttribute('data-active', 'true');
  });

  it('listens to a track without loading it up front', async () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
    open({ library: lib });
    const audio = (await screen.findByText('Calm Lake'))
      .closest('li')!
      .querySelector('audio') as HTMLAudioElement;
    expect(audio).toHaveAttribute('preload', 'none');
    await userEvent.click(screen.getByRole('button', { name: 'Nghe Calm Lake' }));
    expect(play).toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Dừng Calm Lake' })).toBeInTheDocument();
  });

  it('keeps the credit editable and saved', async () => {
    const { saved } = open({ proj: project({ music: MUSIC }) });
    const credit = await screen.findByLabelText('Ghi công');
    expect(credit).toHaveValue(MUSIC.credit);
    await userEvent.type(credit, '!');
    await waitFor(() => expect(lastSaved(saved)?.music?.credit).toBe(`${MUSIC.credit}!`), {
      timeout: 3000,
    });
  });

  it('Không nhạc removes the music and says the video is built without it', async () => {
    const { saved } = open({ proj: project({ music: MUSIC }) });
    const user = userEvent.setup();
    const none = await screen.findByRole('button', { name: 'Không nhạc' });
    expect(none).toHaveAttribute('aria-pressed', 'false');
    await user.click(none);
    await waitFor(() => expect(lastSaved(saved)?.music).toBeNull(), { timeout: 3000 });
    expect(screen.getByRole('button', { name: 'Không nhạc' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.getByText('Video dựng không có nhạc nền.')).toBeInTheDocument();
    expect(screen.queryByLabelText('Ghi công')).not.toBeInTheDocument();
  });

  it('Tải nhạc: uploads a file from this machine, adds it to the library and uses it', async () => {
    let form: FormData | undefined;
    let attached: unknown;
    open({
      extra: {
        'POST /api/music': (_u: string, init?: RequestInit) => {
          form = init?.body as FormData;
          return json(track({ id: 'mine', title: 'Mine' }));
        },
        'POST /api/projects/muoi/music/from-library': (_u: string, init?: RequestInit) => {
          attached = JSON.parse(String(init?.body));
          return json(project({ music: MUSIC }));
        },
      },
    });
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Tải nhạc' }));
    const dialog = await screen.findByRole('dialog', { name: 'Tải nhạc từ máy' });
    const submit = within(dialog).getByRole('button', { name: 'Thêm và dùng' });
    expect(submit).toBeDisabled();
    await user.upload(
      within(dialog).getByLabelText('Thả file nhạc hoặc bấm để chọn'),
      new File(['x'], 'mine.mp3', { type: 'audio/mpeg' }),
    );
    await user.type(within(dialog).getByLabelText(/^Tên bài/), 'Mine');
    await user.type(within(dialog).getByLabelText(/^Nghệ sĩ/), 'Me');
    await user.type(within(dialog).getByLabelText(/^Nguồn/), 'Tự làm');
    await user.type(within(dialog).getByLabelText(/^Giấy phép/), 'CC0');
    await user.type(within(dialog).getByLabelText(/^Tâm trạng/), 'vui, nhanh');
    expect(submit).toBeEnabled();
    await user.click(submit);
    await waitFor(() => expect(attached).toEqual({ id: 'mine' }));
    expect(form?.get('title')).toBe('Mine');
    expect(form?.get('moods')).toBe('vui, nhanh');
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });
});
