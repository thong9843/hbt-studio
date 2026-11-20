import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { DraftCheck } from '../../api/types';
import { json, stubFetch } from '../../test/fakes';
import { project } from '../../test/project';
import { renderWithProviders } from '../../test/render';
import { ToastProvider } from '../Toast';
import { DraftDialog } from './DraftDialog';

afterEach(() => vi.unstubAllGlobals());

const result = (over: Partial<DraftCheck> = {}): DraftCheck => ({
  ok: true,
  errors: [],
  warnings: [],
  topic: 'Vì sao muỗi đốt?',
  series_hint: 'Vì sao…',
  scenes: 3,
  counts: { json: 3, project: 3, after: 3 },
  music_match: null,
  ...over,
});

const bodiesTo = (mock: ReturnType<typeof stubFetch>, suffix: string) =>
  mock.mock.calls
    .filter((c) => String(c[0]).endsWith(suffix))
    .map((c) => JSON.parse(String((c[1] as RequestInit).body)));

function setup(routes: Record<string, unknown> = {}) {
  const mock = stubFetch(routes);
  const onClose = vi.fn();
  renderWithProviders(
    <ToastProvider>
      <Routes>
        <Route path="/" element={<DraftDialog open onClose={onClose} />} />
        <Route path="/p/:slug" element={<p>trang soạn</p>} />
      </Routes>
    </ToastProvider>,
  );
  return { mock, onClose };
}

async function paste(text: string) {
  const dialog = await screen.findByRole('dialog', { name: 'Tạo dự án từ JSON nháp' });
  fireEvent.change(within(dialog).getByLabelText('JSON nháp'), { target: { value: text } });
  return dialog;
}

describe('DraftDialog', () => {
  it('disables Kiểm tra until there is text', async () => {
    setup();
    const dialog = await screen.findByRole('dialog', { name: 'Tạo dự án từ JSON nháp' });
    expect(within(dialog).getByRole('button', { name: 'Kiểm tra' })).toBeDisabled();
    await paste('{}');
    expect(within(dialog).getByRole('button', { name: 'Kiểm tra' })).toBeEnabled();
  });

  it('checks the raw string, shows topic, scenes, music and warnings, then enables Tạo dự án', async () => {
    const user = userEvent.setup();
    const { mock } = setup({
      'POST /api/gd2/draft/check': result({
        music_match: { id: 'curious', title: 'Curious' },
        warnings: [
          { code: 'K16', scene_index: 1, field: 'voice', message: 'Cảnh 2: số 15 chưa có nguồn' },
          { code: 'K10', scene_index: 0, field: 'voice', message: 'từ nhạy cảm', level: 'block' },
          { code: 'K18', scene_index: 2, field: 'image_prompt', message: 'Cảnh 3: thiếu prompt' },
        ],
      }),
    });
    const dialog = await paste('{"hbt_draft": 1}');
    await user.click(within(dialog).getByRole('button', { name: 'Kiểm tra' }));

    expect(await within(dialog).findByText('Vì sao muỗi đốt?')).toBeInTheDocument();
    expect(within(dialog).getByText('Curious')).toBeInTheDocument();
    expect(within(dialog).getByText('3 cảnh báo')).toBeInTheDocument();
    expect(within(dialog).getByText(/số 15 chưa có nguồn/)).toBeInTheDocument();
    expect(within(dialog).getByText(/Sẽ chặn xuất · K10/)).toBeInTheDocument();
    expect(within(dialog).getByText(/Lưu ý · K18/)).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Tạo dự án' })).toBeEnabled();
    expect(bodiesTo(mock, '/gd2/draft/check')).toEqual([{ draft: '{"hbt_draft": 1}' }]);
  });

  it('shows errors, keeps Tạo dự án disabled, and keeps the text when going back', async () => {
    const user = userEvent.setup();
    setup({
      'POST /api/gd2/draft/check': result({
        ok: false,
        scenes: 0,
        topic: '',
        errors: [{ code: 'K13', scene_index: null, field: 'topic', message: "Thiếu 'topic'" }],
      }),
    });
    const dialog = await paste('{"hbt_draft": 1}');
    await user.click(within(dialog).getByRole('button', { name: 'Kiểm tra' }));
    expect(await within(dialog).findByText(/Lỗi · K13/)).toBeInTheDocument();
    expect(within(dialog).getByText('Còn lỗi, sửa JSON rồi kiểm lại')).toBeInTheDocument();
    expect(within(dialog).getByText('Chưa chọn')).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Tạo dự án' })).toBeDisabled();
    await user.click(within(dialog).getByRole('button', { name: 'Sửa JSON' }));
    expect(within(dialog).getByLabelText('JSON nháp')).toHaveValue('{"hbt_draft": 1}');
  });

  it('creates the project and opens the editor', async () => {
    const user = userEvent.setup();
    const { mock, onClose } = setup({
      'POST /api/gd2/draft/check': result(),
      'POST /api/gd2/draft/create': {
        slug: 'vi-sao-muoi-dot',
        project: project({ slug: 'vi-sao-muoi-dot' }),
        warnings: [],
        music_match: null,
      },
    });
    const dialog = await paste('{"hbt_draft": 1}');
    await user.click(within(dialog).getByRole('button', { name: 'Kiểm tra' }));
    await user.click(await within(dialog).findByRole('button', { name: 'Tạo dự án' }));
    expect(await screen.findByText('trang soạn')).toBeInTheDocument();
    expect(onClose).toHaveBeenCalled();
    expect(bodiesTo(mock, '/gd2/draft/create')).toEqual([
      { draft: '{"hbt_draft": 1}', title: null },
    ]);
  });

  it('shows server errors when create answers 422', async () => {
    const user = userEvent.setup();
    setup({
      'POST /api/gd2/draft/check': result(),
      'POST /api/gd2/draft/create': () =>
        json(
          {
            detail: 'JSON nháp có 1 lỗi, chưa tạo',
            errors: [{ code: 'K3', scene_index: 0, field: 'card', message: 'cỡ chữ sai' }],
          },
          422,
        ),
    });
    const dialog = await paste('{"hbt_draft": 1}');
    await user.click(within(dialog).getByRole('button', { name: 'Kiểm tra' }));
    await user.click(await within(dialog).findByRole('button', { name: 'Tạo dự án' }));
    expect(await within(dialog).findByText(/cỡ chữ sai/)).toBeInTheDocument();
    await waitFor(() =>
      expect(within(dialog).getByRole('button', { name: 'Tạo dự án' })).toBeDisabled(),
    );
    expect(screen.queryByText('trang soạn')).not.toBeInTheDocument();
  });

  it('loads a .json file into the box and rejects other files', async () => {
    setup();
    const dialog = await screen.findByRole('dialog', { name: 'Tạo dự án từ JSON nháp' });
    const input = within(dialog).getByTestId('draft-file') as HTMLInputElement;
    const file = new File(['{"hbt_draft": 1}'], 'nhap.json', { type: 'application/json' });
    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() =>
      expect(within(dialog).getByLabelText('JSON nháp')).toHaveValue('{"hbt_draft": 1}'),
    );
    const bad = new File(['x'], 'nhap.txt', { type: 'text/plain' });
    fireEvent.change(input, { target: { files: [bad] } });
    expect(await screen.findByText('Chỉ nhận file .json')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('JSON nháp')).toHaveValue('{"hbt_draft": 1}');
  });
});
