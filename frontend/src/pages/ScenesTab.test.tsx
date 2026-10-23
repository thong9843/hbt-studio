import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Project } from '../api/types';
import { ToastProvider } from '../components/Toast';
import { stubFetch } from '../test/fakes';
import { project, scene } from '../test/project';
import { renderWithProviders } from '../test/render';
import { ComposePage } from './ComposePage';
import { ScenesTab } from './ScenesTab';

afterEach(() => vi.unstubAllGlobals());

const png = () => new Response(new Blob(['png'], { type: 'image/png' }));
const ok = (body: unknown) =>
  new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } });

function setup(initial: Project, extra: Record<string, unknown> = {}) {
  const saved: Project[] = [];
  const routes: Record<string, unknown> = {
    'GET /api/projects/muoi': initial,
    'PUT /api/projects/muoi': (_u: string, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body)) as Project;
      saved.push(body);
      return ok(body);
    },
  };
  for (let i = 0; i < 12; i++) {
    routes[`POST /api/projects/muoi/scenes/${i}/preview.png`] = png;
    routes[`DELETE /api/projects/muoi/scenes/${i}`] = () => {
      const p = saved.length > 0 ? saved[saved.length - 1] : initial;
      const scenes = p.scenes.filter((_, idx) => idx !== i);
      const t = p.thumbnail;
      const thumbnail = t ? { ...t, scene: Math.min(t.scene, scenes.length) } : null;
      const next = { ...p, scenes, thumbnail };
      saved.push(next);
      return ok(next);
    };
  }
  Object.assign(routes, extra);
  stubFetch(routes);
  renderWithProviders(
    <ToastProvider>
      <Routes>
        <Route path="/p/:slug" element={<ComposePage />}>
          <Route index element={<ScenesTab />} />
        </Route>
      </Routes>
    </ToastProvider>,
    '/p/muoi',
  );
  return { saved };
}

describe('ScenesTab', () => {
  it('adds a scene (selects it) and autosaves the new scene count', async () => {
    const { saved } = setup(project());
    await userEvent.click(await screen.findByRole('button', { name: /Thêm cảnh/ }));
    expect(await screen.findByRole('heading', { name: 'Cảnh 4' })).toBeInTheDocument();
    await waitFor(() => expect(saved).toHaveLength(1), { timeout: 3000 });
    expect(saved[0].scenes).toHaveLength(4);
    expect(saved[0].scenes[3].image).toBe('');
  });

  it('removes the last scene after confirmation, and clamps thumbnail.scene', async () => {
    const four = project({
      scenes: [scene(), scene(), scene(), scene()],
      thumbnail: { scene: 4, lines: ['a', 'b'], series: '', accent: '#FFD43B' },
    });
    const { saved } = setup(four);
    const user = userEvent.setup();
    await screen.findByRole('heading', { name: 'Cảnh 1' });
    await user.click(screen.getByText('Cảnh 4'));
    await user.click(screen.getByRole('button', { name: /Xoá cảnh này/ }));
    const dialog = screen.getByRole('alertdialog');
    expect(dialog).toHaveTextContent('Xoá cảnh 4?');
    await user.click(screen.getAllByRole('button', { name: 'Xoá cảnh này' }).at(-1)!);
    await waitFor(() => expect(saved).toHaveLength(1), { timeout: 3000 });
    expect(saved[0].scenes).toHaveLength(3);
    expect((saved[0].thumbnail as { scene: number }).scene).toBe(3);
  });

  it('deletes the scene directly through the DELETE API without reordering', async () => {
    const four = project({ scenes: [scene(), scene(), scene(), scene()] });
    let deletedIndex: number | undefined;
    const { saved } = setup(four, {
      'DELETE /api/projects/muoi/scenes/0': () => {
        deletedIndex = 0;
        const next = { ...four, scenes: four.scenes.slice(1) };
        saved.push(next);
        return ok(next);
      },
    });
    const user = userEvent.setup();
    await screen.findByRole('heading', { name: 'Cảnh 1' });
    await user.click(screen.getByRole('button', { name: /Xoá cảnh này/ }));
    await user.click(screen.getAllByRole('button', { name: 'Xoá cảnh này' }).at(-1)!);
    await waitFor(() => expect(saved).toHaveLength(1), { timeout: 3000 });
    expect(deletedIndex).toBe(0);
    expect(saved[0].scenes).toHaveLength(3);
  });

  it('Ctrl+S saves immediately and Alt+Down moves to the next scene', async () => {
    const { saved } = setup(project());
    const user = userEvent.setup();
    const voice = await screen.findByLabelText('Lời đọc');
    await user.type(voice, ' thêm');
    expect(saved).toHaveLength(0);
    await user.keyboard('{Control>}s{/Control}');
    await waitFor(() => expect(saved).toHaveLength(1));
    await user.keyboard('{Alt>}{ArrowDown}{/Alt}');
    expect(await screen.findByRole('heading', { name: 'Cảnh 2' })).toBeInTheDocument();
  });

  it('warns in yellow when the whole script passes 750 characters', async () => {
    const long = project({
      scenes: [scene({ voice: 'a'.repeat(400) }), scene({ voice: 'b'.repeat(400) }), scene()],
    });
    setup(long);
    expect(await screen.findByText(/Vượt 750 ký tự/)).toBeInTheDocument();
  });
});
