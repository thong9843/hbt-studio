import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Project } from '../api/types';
import { ToastProvider } from '../components/Toast';
import { stubFetch } from '../test/fakes';
import { project, scene } from '../test/project';
import { renderWithProviders } from '../test/render';
import { ComposePage } from './ComposePage';
import { ScenesTab } from './ScenesTab';

const stripProps: { onReorder?: (order: number[], after: number) => void } = {};
vi.mock('../components/compose/SceneStrip', async (orig) => {
  const real = await orig<typeof import('../components/compose/SceneStrip')>();
  return {
    ...real,
    SceneStrip: (props: Parameters<typeof real.SceneStrip>[0]) => {
      stripProps.onReorder = props.onReorder;
      return <real.SceneStrip {...props} />;
    },
  };
});

afterEach(() => vi.unstubAllGlobals());

const png = () => new Response(new Blob(['png'], { type: 'image/png' }));
const ok = (body: unknown) =>
  new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } });
const file = (name: string) => new File(['x'], name, { type: 'image/png' });
const HEADING = 'Cảnh 1 · Thẻ chữ';

function Where() {
  return <output data-testid="where">{useLocation().pathname}</output>;
}

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
  for (let i = 0; i < 12; i++) routes[`POST /api/projects/muoi/scenes/${i}/preview.png`] = png;
  Object.assign(routes, extra);
  const mock = stubFetch(routes);
  renderWithProviders(
    <ToastProvider>
      <Where />
      <Routes>
        <Route path="/p/:slug" element={<ComposePage />}>
          <Route index element={<ScenesTab />} />
          <Route path="export" element={<p>tab xuất</p>} />
        </Route>
      </Routes>
    </ToastProvider>,
    '/p/muoi',
  );
  return { saved, mock };
}

describe('Soạn video — luồng', () => {
  it('multi-drop uploads one file at a time, sorted by name, starting at scene 1', async () => {
    const order: { index: string; name: string }[] = [];
    let current = project({ scenes: [scene(), scene(), scene()] });
    setup(current, {
      'POST /api/projects/muoi/assets': (_u: string, init?: RequestInit) => {
        const form = init?.body as FormData;
        const idx = Number(form.get('scene_index'));
        order.push({ index: String(idx), name: (form.get('file') as File).name });
        current = {
          ...current,
          scenes: current.scenes.map((s, i) =>
            i === idx ? { ...s, image: `images/${idx}.png` } : s,
          ),
        };
        return ok({ kind: 'image', path: `images/${idx}.png`, project: current });
      },
    });
    const user = userEvent.setup();
    await screen.findByRole('heading', { name: HEADING });
    await user.upload(screen.getByLabelText('Thêm ảnh', { selector: 'input' }), [
      file('s10.png'),
      file('s2.png'),
      file('s1.png'),
    ]);
    await waitFor(() => expect(order).toHaveLength(3));
    expect(order).toEqual([
      { index: '0', name: 's1.png' },
      { index: '1', name: 's2.png' },
      { index: '2', name: 's10.png' },
    ]);
    expect(await screen.findByText('Đã gán 3 ảnh')).toBeInTheDocument();
  });

  it('shows a Toast with the busy hint when reordering fails with 409 (rendering)', async () => {
    setup(project(), {
      'POST /api/projects/muoi/scenes/reorder': () =>
        new Response(JSON.stringify({ detail: 'Đang dựng' }), {
          status: 409,
          headers: { 'Content-Type': 'application/json' },
        }),
    });
    await screen.findByRole('heading', { name: HEADING });
    stripProps.onReorder?.([1, 0, 2], 1);
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Đang dựng');
    expect(screen.getByRole('button', { name: 'Thử lại' })).toBeInTheDocument();
  });

  it('opens "Bìa & đăng" from the header bar; Dán JSON and the ⋯ menu stay hidden (Đợt 4)', async () => {
    setup(project());
    const user = userEvent.setup();
    await screen.findByRole('heading', { name: HEADING });
    expect(screen.queryByRole('button', { name: /Dán JSON/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Bản sao lưu|Hoàn tác/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '⋯' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Bìa & đăng' }));
    expect(await screen.findByRole('dialog', { name: 'Bìa & đăng' })).toBeInTheDocument();
  });

  it('keeps Xem nhanh / Xuất bản đẹp off with the reason until the materials are ready', async () => {
    setup(project({ voice: null }));
    await screen.findByRole('heading', { name: HEADING });
    const fast = screen.getByRole('button', { name: /Xem nhanh/ });
    expect(fast).toBeDisabled();
    expect(fast).toHaveAttribute('title', 'Thiếu ảnh cảnh 3 · Thiếu giọng đọc');
  });

  it('when ready, Xem nhanh only switches to the export tab (no render started)', async () => {
    const ready = project({
      voice: 'voice.wav',
      scenes: [scene({ image: 'a.png' }), scene({ image: 'b.png' }), scene({ image: 'c.png' })],
    });
    const { mock } = setup(ready);
    const user = userEvent.setup();
    await screen.findByRole('heading', { name: HEADING });
    await user.click(screen.getByRole('button', { name: 'Xem nhanh' }));
    expect(screen.getByTestId('where')).toHaveTextContent('/p/muoi/export');
    expect(JSON.stringify(mock.mock.calls)).not.toMatch(/\/render"|\/renders/);
  });

  it('renames the project from the header and autosaves', async () => {
    const { saved } = setup(project());
    const user = userEvent.setup();
    const title = await screen.findByLabelText('Tiêu đề');
    await user.type(title, ' 2');
    await waitFor(() => expect(saved.at(-1)?.title).toBe('Muỗi 2'), { timeout: 3000 });
    expect(await screen.findByText('Đã lưu')).toBeInTheDocument();
  });
});

describe('Soạn video — dưới 1024 px', () => {
  it('moves the preview into a drawer opened by a floating button', async () => {
    const original = window.matchMedia;
    window.matchMedia = ((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener() {},
      removeEventListener() {},
      addListener() {},
      removeListener() {},
      dispatchEvent: () => false,
    })) as typeof window.matchMedia;
    try {
      const { mock } = setup(project());
      const user = userEvent.setup();
      await screen.findByRole('heading', { name: HEADING });
      const calls = () => mock.mock.calls.filter(([u]) => String(u).includes('preview.png')).length;
      expect(calls()).toBe(0); // chưa mở ngăn kéo thì không vẽ
      await user.click(screen.getByRole('button', { name: 'Xem trước' }));
      const drawer = await screen.findByRole('dialog', { name: 'Xem trước' });
      expect(within(drawer).getByRole('button', { name: 'Vùng an toàn' })).toBeInTheDocument();
      await waitFor(() => expect(calls()).toBeGreaterThan(0), { timeout: 3000 });
    } finally {
      window.matchMedia = original;
    }
  });
});
