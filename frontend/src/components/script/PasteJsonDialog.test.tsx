import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { json } from '../../test/fakes';
import { PasteJsonDialog } from './PasteJsonDialog';
import { bodiesTo, checkResult, paste, setup } from './scriptTestKit';

afterEach(() => vi.unstubAllGlobals());

const open = (routes: Record<string, unknown> = {}) =>
  setup(<PasteJsonDialog open onClose={() => {}} />, routes);

const diffCard = {
  scene_index: 0,
  field: 'card',
  before: { y: 'top', lines: [{ text: 'Cũ', size: 's', color: 'ink' }] },
  after: { y: 'upper', lines: [{ text: 'GẦN 900 TƯỢNG ĐÁ', size: 'l', color: 'primary' }] },
};

describe('PasteJsonDialog — Dán và Kiểm tra', () => {
  it('disables Kiểm tra until there is text', async () => {
    open();
    const dialog = await screen.findByRole('dialog', { name: 'Dán JSON kịch bản' });
    expect(within(dialog).getByRole('button', { name: 'Kiểm tra' })).toBeDisabled();
    await paste('[]');
    expect(within(dialog).getByRole('button', { name: 'Kiểm tra' })).toBeEnabled();
  });

  it('checks the raw string and shows counts, diff, warnings and the realign note', async () => {
    const user = userEvent.setup();
    const mock = open({
      'POST /api/projects/muoi/script/check': checkResult({
        diff: [diffCard, { scene_index: 1, field: 'punch', before: false, after: true }],
        warnings: [
          { code: 'K5', scene_index: 0, field: 'card', message: 'Dòng 1 dài quá' },
          { code: 'K9', scene_index: null, field: 'voice', message: 'Tổng lời đọc quá dài' },
        ],
        realign_scenes: [1],
      }),
    });
    const dialog = await paste('[{"punch": true}]');
    await user.click(within(dialog).getByRole('button', { name: 'Kiểm tra' }));

    expect(await within(dialog).findByText('3 = 3')).toBeInTheDocument();
    expect(within(dialog).getByText('GẦN 900 TƯỢNG ĐÁ')).toBeInTheDocument();
    expect(within(dialog).getByText('Cảnh 1')).toBeInTheDocument();
    expect(within(dialog).getByText('Cảnh 2')).toBeInTheDocument();
    expect(within(dialog).getByText(/Dòng 1 dài quá/)).toBeInTheDocument();
    expect(within(dialog).getByText(/Tổng lời đọc quá dài/)).toBeInTheDocument();
    expect(within(dialog).getByText('1 cảnh sẽ căn chữ lại ở lần dựng tới')).toBeInTheDocument();
    expect(within(dialog).getByText(/Giữ nguyên:/)).toBeInTheDocument();
    expect(bodiesTo(mock, '/script/check')).toEqual([{ script: '[{"punch": true}]', extra: null }]);
  });

  it('shows K1 errors with line:col and keeps the text when going back', async () => {
    const user = userEvent.setup();
    open({
      'POST /api/projects/muoi/script/check': checkResult({
        ok: false,
        counts: { json: 0, project: 3, after: 3 },
        errors: [
          { code: 'K1', scene_index: null, field: '$', message: 'JSON lỗi ở dòng 2, cột 5' },
        ],
      }),
    });
    const dialog = await paste('[{');
    await user.click(within(dialog).getByRole('button', { name: 'Kiểm tra' }));
    expect(await within(dialog).findByText(/dòng 2, cột 5/)).toBeInTheDocument();
    expect(within(dialog).getByText('0 ≠ 3')).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Sửa JSON' }));
    expect(within(dialog).getByLabelText('JSON kịch bản')).toHaveValue('[{');
  });

  it('marks K10 block warnings as "Sẽ chặn xuất"', async () => {
    const user = userEvent.setup();
    open({
      'POST /api/projects/muoi/script/check': checkResult({
        warnings: [
          { code: 'K10', scene_index: 2, field: 'voice', message: 'có từ máu', level: 'block' },
        ],
      }),
    });
    const dialog = await paste('[]');
    await user.click(within(dialog).getByRole('button', { name: 'Kiểm tra' }));
    expect(await within(dialog).findByText(/Sẽ chặn xuất · K10/)).toBeInTheDocument();
  });

  it('collapses added scenes into "+k cảnh mới"', async () => {
    const user = userEvent.setup();
    open({
      'POST /api/projects/muoi/script/check': checkResult({
        counts: { json: 5, project: 3, after: 5 },
        diff: [
          { scene_index: 3, field: 'scene', before: null, after: { voice: 'Cảnh bốn' } },
          { scene_index: 4, field: 'scene', before: null, after: { voice: 'Cảnh năm' } },
        ],
      }),
    });
    const dialog = await paste('[]');
    await user.click(within(dialog).getByRole('button', { name: 'Kiểm tra' }));
    const toggle = await within(dialog).findByRole('button', { name: '+2 cảnh mới' });
    expect(within(dialog).queryByText('Cảnh bốn')).toBeNull();
    await user.click(toggle);
    expect(within(dialog).getByText('Cảnh bốn')).toBeInTheDocument();
  });

  it('offers Thêm cảnh / Bỏ phần thừa for surplus scenes and re-checks with extra', async () => {
    const user = userEvent.setup();
    const mock = open({
      'POST /api/projects/muoi/script/check': (_u: string, init?: RequestInit) => {
        const { extra } = JSON.parse(String(init?.body));
        return json(
          extra
            ? checkResult({ counts: { json: 5, project: 3, after: extra === 'add' ? 5 : 3 } })
            : checkResult({
                ok: false,
                counts: { json: 5, project: 3, after: 3 },
                errors: [{ code: 'K2', scene_index: null, field: 'scenes', message: 'thừa' }],
              }),
        );
      },
    });
    const dialog = await paste('[]');
    await user.click(within(dialog).getByRole('button', { name: 'Kiểm tra' }));
    await user.click(await within(dialog).findByRole('button', { name: 'Thêm cảnh' }));
    await waitFor(() =>
      expect(within(dialog).getByRole('button', { name: 'Thêm cảnh' })).toHaveAttribute(
        'aria-pressed',
        'true',
      ),
    );
    expect(bodiesTo(mock, '/script/check').map((b) => b.extra)).toEqual([null, 'add']);
  });

  it('reads a chosen .json file into the box', async () => {
    const user = userEvent.setup();
    open();
    const dialog = await screen.findByRole('dialog', { name: 'Dán JSON kịch bản' });
    await user.upload(
      within(dialog).getByTestId('script-file'),
      new File(['[{"punch":true}]'], 'kich-ban.json', { type: 'application/json' }),
    );
    await waitFor(() =>
      expect(within(dialog).getByLabelText('JSON kịch bản')).toHaveValue('[{"punch":true}]'),
    );
  });
});
