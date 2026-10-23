import { act, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Project, RenderRecord } from '../api/types';
import { stubFetch } from '../test/fakes';
import { project } from '../test/project';
import { renderWithProviders } from '../test/render';
import { AudioTab } from './AudioTab';
import { ComposePage } from './ComposePage';
import { ScenesTab } from './ScenesTab';

afterEach(() => vi.unstubAllGlobals());

const png = () => new Response(new Blob(['png'], { type: 'image/png' }), { status: 200 });

function routes(extra: Record<string, unknown> = {}) {
  const saved: Project[] = [];
  const previews: { index: string; body: { scene: { card: { lines: { text: string }[] } } } }[] =
    [];
  const mock = stubFetch({
    'GET /api/projects/muoi': project(),
    'PUT /api/projects/muoi': (_url: string, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body)) as Project;
      saved.push(body);
      return new Response(JSON.stringify(body), {
        headers: { 'Content-Type': 'application/json' },
      });
    },
    'POST /api/projects/muoi/scenes/0/preview.png': (_u: string, init?: RequestInit) => {
      previews.push({ index: '0', body: JSON.parse(String(init?.body)) });
      return png();
    },
    'POST /api/projects/muoi/scenes/1/preview.png': png,
    'POST /api/projects/muoi/scenes/2/preview.png': png,
    ...extra,
  });
  return { mock, saved, previews };
}

function page(children = <ScenesTab />) {
  return renderWithProviders(
    <Routes>
      <Route path="/p/:slug" element={<ComposePage />}>
        <Route index element={children} />
        <Route path="audio" element={<AudioTab />} />
      </Route>
    </Routes>,
    '/p/muoi',
  );
}

describe('Compose page', () => {
  it('lists the scenes (numbered from 1) and edits the selected one', async () => {
    routes();
    const user = userEvent.setup();
    page();
    expect(await screen.findByRole('heading', { name: 'Cảnh 1' })).toBeInTheDocument();
    expect(screen.getByText('Cảnh 3')).toBeInTheDocument();
    expect(screen.getByText('chưa có ảnh')).toBeInTheDocument();
    await user.click(screen.getByText('Cảnh 2'));
    expect(screen.getByRole('heading', { name: 'Cảnh 2' })).toBeInTheDocument();
  });

  it('autosaves 1 s after typing and shows the saved indicator', async () => {
    const { saved } = routes();
    const user = userEvent.setup();
    page();
    const voice = await screen.findByLabelText('Lời đọc');
    await user.clear(voice);
    await user.type(voice, 'Muỗi thích bạn');
    expect(saved).toHaveLength(0);
    expect(screen.getByText('Chưa lưu…')).toBeInTheDocument();
    await waitFor(() => expect(saved).toHaveLength(1), { timeout: 3000 });
    expect(saved[0].scenes[0].voice).toBe('Muỗi thích bạn');
    expect(saved[0].slug).toBe('muoi');
    expect(await screen.findByText('Đã lưu')).toBeInTheDocument();
  });

  it('shows character counts and warns past the 750 limit', async () => {
    routes();
    page();
    await screen.findByLabelText('Lời đọc');
    expect(screen.getByText(/Cả video: 26\/750 ký tự/)).toBeInTheDocument();
  });

  it('draws the draft preview 600 ms after typing stops, not on every key', async () => {
    const { previews } = routes();
    const user = userEvent.setup();
    page();
    const text = await screen.findByLabelText('Dòng 1: Chữ');
    await waitFor(() => expect(previews.length).toBeGreaterThanOrEqual(1));
    const before = previews.length;
    await user.type(text, ' mới');
    await act(async () => {
      await new Promise((r) => setTimeout(r, 900));
    });
    expect(previews.length).toBe(before + 1);
    expect(previews.at(-1)?.body.scene.card.lines[0].text).toBe('Tiêu đề mới');
  });

  it('adds and removes card lines', async () => {
    routes();
    const user = userEvent.setup();
    page();
    await screen.findByLabelText('Dòng 1: Chữ');
    await user.click(screen.getByRole('button', { name: 'Thêm dòng' }));
    expect(screen.getByLabelText('Dòng 2: Chữ')).toBeInTheDocument();
    await user.click(screen.getAllByRole('button', { name: 'Bỏ dòng' })[0]);
    expect(screen.queryByLabelText('Dòng 2: Chữ')).not.toBeInTheDocument();
  });

  it('uploads a dropped image for the right scene index and updates the thumbnail', async () => {
    let form: FormData | undefined;
    routes({
      'POST /api/projects/muoi/assets': (_u: string, init?: RequestInit) => {
        form = init?.body as FormData;
        return new Response(
          JSON.stringify({
            kind: 'image',
            path: 'images/scene-01.png',
            project: project({
              scenes: [
                { ...project().scenes[0], image: 'images/scene-01.png' },
                ...project().scenes.slice(1),
              ],
            }),
          }),
          { headers: { 'Content-Type': 'application/json' } },
        );
      },
    });
    const user = userEvent.setup();
    page();
    const input = await screen.findByLabelText('Ảnh cảnh');
    await user.upload(input, new File(['x'], 'a.png', { type: 'image/png' }));
    await waitFor(() => expect(form).toBeDefined());
    expect(form?.get('kind')).toBe('image');
    expect(form?.get('scene_index')).toBe('0');
  });

  it('keeps the music credit editable and saved', async () => {
    const { saved } = routes({
      'GET /api/projects/muoi': project({
        music: { file: 'music.mp3', start: null, credit: 'Bài – Ai (Pixabay)' },
      }),
      'GET /api/music': [],
    });
    const user = userEvent.setup();
    renderWithProviders(
      <Routes>
        <Route path="/p/:slug" element={<ComposePage />}>
          <Route path="audio" element={<AudioTab />} />
        </Route>
      </Routes>,
      '/p/muoi/audio',
    );
    const credit = await screen.findByLabelText('Ghi công');
    await user.type(credit, '!');
    await waitFor(() => expect(saved).toHaveLength(1), { timeout: 3000 });
    expect(saved[0].music?.credit).toBe('Bài – Ai (Pixabay)!');
  });

  describe('Audio tab: music.start', () => {
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

    function openAudio(renders: RenderRecord[], start: number | null = null) {
      const ctx = routes({
        'GET /api/projects/muoi': project({
          music: { file: 'music.mp3', start, credit: 'Bài – Ai (Pixabay)' },
        }),
        'GET /api/music': [],
        'GET /api/projects/muoi/renders': renders,
      });
      renderWithProviders(
        <Routes>
          <Route path="/p/:slug" element={<ComposePage />}>
            <Route path="audio" element={<AudioTab />} />
          </Route>
        </Routes>,
        '/p/muoi/audio',
      );
      return ctx;
    }

    it('saves a typed start and clears it back to automatic', async () => {
      const { saved } = openAudio([]);
      const user = userEvent.setup();
      const input = await screen.findByLabelText('Bắt đầu nhạc tại giây');
      await user.type(input, '7');
      await waitFor(() => expect(saved.at(-1)?.music?.start).toBe(7), { timeout: 3000 });
      await user.clear(input);
      await waitFor(() => expect(saved.at(-1)?.music?.start).toBeNull(), { timeout: 3000 });
    });

    it('shows the second the last render picked and fills it in with one click', async () => {
      const { saved } = openAudio([render()]);
      const user = userEvent.setup();
      expect(await screen.findByText('Lần dựng gần nhất app chọn giây 12.')).toBeInTheDocument();
      await user.click(screen.getByRole('button', { name: 'Dùng giá trị này' }));
      expect(screen.getByLabelText('Bắt đầu nhạc tại giây')).toHaveValue(12);
      await waitFor(() => expect(saved.at(-1)?.music?.start).toBe(12), { timeout: 3000 });
      expect(screen.queryByRole('button', { name: 'Dùng giá trị này' })).not.toBeInTheDocument();
    });

    it('explains that nothing is known before the first render', async () => {
      openAudio([]);
      expect(await screen.findByText(/Chưa có lần dựng nào/)).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Dùng giá trị này' })).not.toBeInTheDocument();
    });

    it('hides the stale second and says the music changed', async () => {
      openAudio([render({ music_matches_current: false })]);
      expect(await screen.findByText(/Nhạc đã đổi sau lần dựng gần nhất/)).toBeInTheDocument();
      expect(screen.queryByText(/app chọn giây/)).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Dùng giá trị này' })).not.toBeInTheDocument();
    });

    it('ignores a last render whose start was set by hand', async () => {
      openAudio([render({ music_start: 3, music_start_source: 'manual' })]);
      expect(await screen.findByText(/Chưa có lần dựng nào/)).toBeInTheDocument();
    });

    it('does not offer the button when start is already set', async () => {
      openAudio([render()], 5);
      await screen.findByLabelText('Bắt đầu nhạc tại giây');
      expect(screen.queryByRole('button', { name: 'Dùng giá trị này' })).not.toBeInTheDocument();
    });

    it('plays the 10 s preview from the chosen second', async () => {
      const play = vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
      vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => undefined);
      openAudio([render()]);
      const user = userEvent.setup();
      await screen.findByText('Lần dựng gần nhất app chọn giây 12.');
      await user.click(screen.getByRole('button', { name: 'Nghe thử 10 giây' }));
      expect(play).toHaveBeenCalled();
      const snippet = document.querySelector('audio:not([controls])') as HTMLAudioElement;
      expect(snippet.currentTime).toBe(12);
      play.mockRestore();
    });
  });
});
