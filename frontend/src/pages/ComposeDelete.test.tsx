import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider } from '../components/Toast';
import { FakeEventSource, stubFetch } from '../test/fakes';
import { project } from '../test/project';
import { renderWithProviders } from '../test/render';
import { ComposePage } from './ComposePage';
import { ScenesTab } from './ScenesTab';

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal('EventSource', FakeEventSource);
});
afterEach(() => vi.unstubAllGlobals());

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

function open(extra: Record<string, unknown> = {}) {
  const calls: string[] = [];
  const mock = stubFetch({
    'GET /api/projects/muoi': project(),
    'PUT /api/projects/muoi': (_u: string, init?: RequestInit) => {
      calls.push('PUT');
      return json(JSON.parse(String(init?.body)));
    },
    'DELETE /api/projects/muoi': () => {
      calls.push('DELETE');
      return new Response(null, { status: 204 });
    },
    'POST /api/projects/muoi/scenes/0/preview.png': () => new Response(new Blob(['x'])),
    'POST /api/projects/muoi/scenes/1/preview.png': () => new Response(new Blob(['x'])),
    'POST /api/projects/muoi/scenes/2/preview.png': () => new Response(new Blob(['x'])),
    ...extra,
  });
  renderWithProviders(
    <ToastProvider>
      <Routes>
        <Route path="/p/:slug" element={<ComposePage />}>
          <Route index element={<ScenesTab />} />
        </Route>
        <Route path="/projects" element={<p>Danh sách dự án</p>} />
      </Routes>
    </ToastProvider>,
    '/p/muoi',
  );
  return { calls, mock };
}

async function openDeleteDialog(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole('button', { name: 'Thêm thao tác' }));
  await user.click(screen.getByRole('menuitem', { name: 'Xoá dự án' }));
  return screen.findByRole('alertdialog', { name: 'Xoá dự án?' });
}

describe('Soạn video: Xoá dự án ở menu ⋯ cạnh tên dự án', () => {
  it('asks first; Huỷ keeps the project and calls nothing', async () => {
    const user = userEvent.setup();
    const { calls } = open();
    const dialog = await openDeleteDialog(user);
    expect(dialog).toHaveTextContent('Việc này không hoàn tác được');
    await user.click(within(dialog).getByRole('button', { name: 'Huỷ' }));
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
    expect(calls).toEqual([]);
    expect(screen.queryByText('Danh sách dự án')).toBeNull();
  });

  it('confirm: saves pending edits first, deletes, and goes back to the project list', async () => {
    const user = userEvent.setup();
    const { calls } = open();
    const title = await screen.findByLabelText('Tiêu đề');
    await user.type(title, ' mới'); // còn lần lưu tự động đang chờ
    const dialog = await openDeleteDialog(user);
    await user.click(within(dialog).getByRole('button', { name: 'Xoá' }));
    expect(await screen.findByText('Danh sách dự án')).toBeInTheDocument();
    expect(calls).toEqual(['PUT', 'DELETE']); // lưu nốt rồi mới xoá; không có PUT nào sau DELETE
    await new Promise((r) => setTimeout(r, 1300));
    expect(calls).toEqual(['PUT', 'DELETE']);
  });

  it('shows a Toast and stays on the page when the server refuses (409)', async () => {
    const user = userEvent.setup();
    const { calls } = open({
      'DELETE /api/projects/muoi': () => json({ detail: 'Project đang được dựng' }, 409),
    });
    const dialog = await openDeleteDialog(user);
    await user.click(within(dialog).getByRole('button', { name: 'Xoá' }));
    expect((await screen.findAllByText(/đang được dựng/)).length).toBeGreaterThan(0);
    expect(screen.queryByText('Danh sách dự án')).toBeNull();
    expect(calls).not.toContain('DELETE');
  });

  it('is turned off while this project is rendering', async () => {
    const user = userEvent.setup();
    open({
      'GET /api/jobs': [
        { id: 'j9', slug: 'muoi', kind: 'final', status: 'running', progress: 10, step: 'Ghép' },
      ],
    });
    await user.click(await screen.findByRole('button', { name: 'Thêm thao tác' }));
    const item = screen.getByRole('menuitem', { name: 'Xoá dự án' });
    await waitFor(() => expect(item).toBeDisabled());
    expect(item).toHaveAttribute('title', 'Đang dựng');
  });
});
