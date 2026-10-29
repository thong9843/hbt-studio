import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useNewProject } from '../hooks/newProject';
import { stubFetch } from '../test/fakes';
import { project } from '../test/project';
import { renderWithProviders } from '../test/render';
import { NewProjectProvider } from './NewProjectDialog';

afterEach(() => vi.unstubAllGlobals());

function Opener() {
  const { open } = useNewProject();
  return (
    <button type="button" onClick={() => open()}>
      mở hộp
    </button>
  );
}

function app() {
  return renderWithProviders(
    <NewProjectProvider>
      <Routes>
        <Route path="/" element={<Opener />} />
        <Route path="/p/:slug" element={<p>trang soạn</p>} />
        <Route path="/postv/:slug" element={<p>trang PostV</p>} />
      </Routes>
    </NewProjectProvider>,
  );
}

const created = () =>
  vi.fn((_url: string, init?: RequestInit) => {
    void init;
    return new Response(JSON.stringify(project({ slug: 'video-moi', title: 'Video mới' })), {
      status: 201,
      headers: { 'Content-Type': 'application/json' },
    });
  });

async function openDialog(user: ReturnType<typeof userEvent.setup>) {
  app();
  await user.click(screen.getByRole('button', { name: 'mở hộp' }));
  return screen.findByRole('dialog', { name: 'Tạo video mới' });
}

describe('NewProjectDialog', () => {
  it('creates with the defaults (no series, 8 scenes) and opens the editor', async () => {
    const user = userEvent.setup();
    const create = created();
    stubFetch({ 'POST /api/projects': create });
    await openDialog(user);
    expect(screen.getByRole('button', { name: '8' })).toHaveAttribute('aria-pressed', 'true');
    await user.type(screen.getByLabelText('Tiêu đề'), 'Video mới');
    await user.click(screen.getByRole('button', { name: 'Tạo' }));
    expect(await screen.findByText('trang soạn')).toBeInTheDocument();
    expect(JSON.parse(String(create.mock.calls[0][1]?.body))).toEqual({
      title: 'Video mới',
      series: '',
      scene_count: 8,
    });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('offers the kind (Video HBT is selected by default)', async () => {
    const user = userEvent.setup();
    stubFetch({});
    await openDialog(user);
    expect(screen.getByRole('button', { name: 'Video HBT' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.getByRole('button', { name: 'PostV' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('PostV: hides the scene count, sends kind postv and opens the PostV screen', async () => {
    const user = userEvent.setup();
    const create = vi.fn((_url: string, init?: RequestInit) => {
      void init;
      return new Response(
        JSON.stringify({ version: 1, kind: 'postv', slug: 'bai-moi', title: 'Bài mới' }),
        { status: 201, headers: { 'Content-Type': 'application/json' } },
      );
    });
    stubFetch({ 'POST /api/projects': create });
    await openDialog(user);
    await user.click(screen.getByRole('button', { name: 'PostV' }));
    expect(screen.queryByRole('button', { name: '8' })).toBeNull();
    await user.type(screen.getByLabelText('Tiêu đề'), 'Bài mới');
    await user.click(screen.getByRole('button', { name: 'Tạo' }));
    expect(await screen.findByText('trang PostV')).toBeInTheDocument();
    expect(JSON.parse(String(create.mock.calls[0][1]?.body))).toEqual({
      title: 'Bài mới',
      series: '',
      kind: 'postv',
    });
  });

  it('puts focus on the title field', async () => {
    const user = userEvent.setup();
    stubFetch({});
    await openDialog(user);
    expect(screen.getByLabelText('Tiêu đề')).toHaveFocus();
  });

  it('keeps Create off until a title is typed', async () => {
    const user = userEvent.setup();
    stubFetch({});
    await openDialog(user);
    expect(screen.getByRole('button', { name: 'Tạo' })).toBeDisabled();
    await user.type(screen.getByLabelText('Tiêu đề'), '  ');
    expect(screen.getByRole('button', { name: 'Tạo' })).toBeDisabled();
    await user.type(screen.getByLabelText('Tiêu đề'), 'A');
    expect(screen.getByRole('button', { name: 'Tạo' })).toBeEnabled();
  });

  it('sends the chosen preset series and scene count; a chip toggles off', async () => {
    const user = userEvent.setup();
    const create = created();
    stubFetch({ 'POST /api/projects': create });
    await openDialog(user);
    const preset = screen.getByRole('button', { name: 'Vì sao Trái Đất' });
    await user.click(preset);
    expect(preset).toHaveAttribute('aria-pressed', 'true');
    await user.click(screen.getByRole('button', { name: '3' }));
    await user.click(screen.getByRole('button', { name: '12' }));
    expect(screen.getByRole('button', { name: '3' })).toHaveAttribute('aria-pressed', 'false');
    await user.type(screen.getByLabelText('Tiêu đề'), 'Bầu trời');
    await user.click(screen.getByRole('button', { name: 'Tạo' }));
    await screen.findByText('trang soạn');
    expect(JSON.parse(String(create.mock.calls[0][1]?.body))).toEqual({
      title: 'Bầu trời',
      series: 'Vì sao Trái Đất',
      scene_count: 12,
    });
  });

  it.each(['Vì Sao', 'Vì sao Trái Đất', 'Vì sao vậy ta?'])(
    'chip "%s" stores exactly its own text as series (it is printed on the cover)',
    async (label) => {
      const user = userEvent.setup();
      const create = created();
      stubFetch({ 'POST /api/projects': create });
      await openDialog(user);
      await user.click(screen.getByRole('button', { name: label }));
      await user.type(screen.getByLabelText('Tiêu đề'), 'X');
      await user.click(screen.getByRole('button', { name: 'Tạo' }));
      await screen.findByText('trang soạn');
      expect(JSON.parse(String(create.mock.calls[0][1]?.body)).series).toBe(label);
    },
  );

  it('offers exactly the scene counts 3 to 12', async () => {
    const user = userEvent.setup();
    stubFetch({});
    await openDialog(user);
    const group = screen.getByRole('group', { name: 'Số cảnh' });
    const labels = Array.from(group.querySelectorAll('button')).map((b) => b.textContent);
    expect(labels).toEqual(['3', '4', '5', '6', '7', '8', '9', '10', '11', '12']);
  });

  it('"Khác" reveals a free series field and sends its trimmed text', async () => {
    const user = userEvent.setup();
    const create = created();
    stubFetch({ 'POST /api/projects': create });
    await openDialog(user);
    expect(screen.queryByPlaceholderText('Tên series')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Khác' }));
    await user.type(screen.getByPlaceholderText('Tên series'), '  Chuyện lạ ');
    await user.type(screen.getByLabelText('Tiêu đề'), 'X');
    await user.click(screen.getByRole('button', { name: 'Tạo' }));
    await screen.findByText('trang soạn');
    expect(JSON.parse(String(create.mock.calls[0][1]?.body)).series).toBe('Chuyện lạ');
  });

  it('shows the API error inside the dialog and stays open', async () => {
    const user = userEvent.setup();
    stubFetch({
      'POST /api/projects': () =>
        new Response(JSON.stringify({ detail: 'Tiêu đề trùng' }), {
          status: 409,
          headers: { 'Content-Type': 'application/json' },
        }),
    });
    await openDialog(user);
    await user.type(screen.getByLabelText('Tiêu đề'), 'A');
    await user.click(screen.getByRole('button', { name: 'Tạo' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Tiêu đề trùng'));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('Cancel closes without creating, and reopening starts clean', async () => {
    const user = userEvent.setup();
    const create = created();
    stubFetch({ 'POST /api/projects': create });
    await openDialog(user);
    await user.type(screen.getByLabelText('Tiêu đề'), 'Nháp');
    await user.click(screen.getByRole('button', { name: 'Huỷ' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(create).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'mở hộp' }));
    expect(await screen.findByLabelText('Tiêu đề')).toHaveValue('');
  });

  it('closes on Escape', async () => {
    const user = userEvent.setup();
    stubFetch({});
    await openDialog(user);
    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });
});
