import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Project } from '../api/types';
import { stubFetch } from '../test/fakes';
import { project } from '../test/project';
import { renderWithProviders } from '../test/render';
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
    expect(await screen.findByRole('heading', { name: 'Cảnh 1 · Thẻ chữ' })).toBeInTheDocument();
    const strip = screen.getByRole('region', { name: 'Các cảnh' });
    expect(
      within(strip).getByRole('button', { name: /^Cảnh 3 — chưa có ảnh/ }),
    ).toBeInTheDocument();
    await user.click(within(strip).getByRole('button', { name: /^Cảnh 2/ }));
    expect(screen.getByRole('heading', { name: 'Cảnh 2 · Thẻ chữ' })).toBeInTheDocument();
  });

  it('autosaves 1 s after typing and shows the saved indicator', async () => {
    const { saved } = routes();
    const user = userEvent.setup();
    page();
    const voice = await screen.findByLabelText('Lời đọc cảnh');
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
    await screen.findByLabelText('Lời đọc cảnh');
    expect(screen.getByText('Cả video 26/750')).toBeInTheDocument();
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
    await user.click(screen.getByRole('button', { name: /^Dòng$/ }));
    expect(screen.getByLabelText('Dòng 2: Chữ')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Bỏ dòng 1' }));
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
});
