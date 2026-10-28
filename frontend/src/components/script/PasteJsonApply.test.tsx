import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useRenderJob } from '../../hooks/renderJob';
import { FakeEventSource, json } from '../../test/fakes';
import { project, scene } from '../../test/project';
import { PasteJsonDialog } from './PasteJsonDialog';
import { bodiesTo, checkResult, paste, setup } from './scriptTestKit';

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal('EventSource', FakeEventSource);
});
afterEach(() => vi.unstubAllGlobals());

function Host() {
  const job = useRenderJob();
  const [isOpen, setOpen] = useState(true);
  return (
    <>
      <button type="button" onClick={() => void job.start('muoi', {})}>
        bắt đầu dựng
      </button>
      <PasteJsonDialog open={isOpen} onClose={() => setOpen(false)} />
    </>
  );
}

const open = (routes: Record<string, unknown> = {}, child = <Host />) =>
  setup(child, {
    'POST /api/projects/muoi/script/check': checkResult({
      counts: { json: 2, project: 3, after: 3 },
      diff: [{ scene_index: 0, field: 'punch', before: false, after: true }],
    }),
    'POST /api/projects/muoi/render': { job_id: 'j1' },
    ...routes,
  });

const applied = project({
  scenes: [scene({ punch: true, image: 'images/scene-01.png' }), scene(), scene()],
});

async function toCheckStep(text = '[{"punch":true},{"punch":false}]') {
  const user = userEvent.setup();
  const dialog = await paste(text);
  await user.click(within(dialog).getByRole('button', { name: 'Kiểm tra' }));
  await within(dialog).findByText('Cảnh 1');
  return { user, dialog };
}

describe('PasteJsonDialog — Áp dụng', () => {
  it('applies "n cảnh" with the base_hash from the check and toasts with Hoàn tác', async () => {
    const mock = open({
      'POST /api/projects/muoi/script/apply': {
        project: applied,
        backup_id: 'b1',
        base_hash: 'h2',
      },
    });
    const { user, dialog } = await toCheckStep();
    await user.click(within(dialog).getByRole('button', { name: 'Áp dụng 2 cảnh' }));

    expect(await screen.findByText('Đã áp dụng 2 cảnh')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Hoàn tác' })).toBeInTheDocument();
    expect(bodiesTo(mock, '/script/apply')).toEqual([
      { script: '[{"punch":true},{"punch":false}]', extra: null, base_hash: 'h1' },
    ]);
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('Hoàn tác restores the backup returned by apply (no confirmation)', async () => {
    const mock = open({
      'POST /api/projects/muoi/script/apply': {
        project: applied,
        backup_id: 'b1',
        base_hash: 'h2',
      },
      'POST /api/projects/muoi/backups/b1/restore': {
        project: project(),
        backup_id: 'b2',
        base_hash: 'h1',
      },
    });
    const { user, dialog } = await toCheckStep();
    await user.click(within(dialog).getByRole('button', { name: 'Áp dụng 2 cảnh' }));
    await user.click(await screen.findByRole('button', { name: 'Hoàn tác' }));
    expect(await screen.findByText('Đã hoàn tác')).toBeInTheDocument();
    expect(mock.mock.calls.some((c) => String(c[0]).endsWith('/backups/b1/restore'))).toBe(true);
  });

  it('disables Áp dụng while there are errors', async () => {
    open({
      'POST /api/projects/muoi/script/check': checkResult({
        ok: false,
        errors: [{ code: 'K3', scene_index: 0, field: 'card.y', message: 'y sai' }],
      }),
    });
    const { dialog } = await toCheckStep();
    expect(within(dialog).getByRole('button', { name: 'Áp dụng 3 cảnh' })).toBeDisabled();
    expect(within(dialog).getByText('Còn lỗi, sửa JSON rồi kiểm lại')).toBeInTheDocument();
  });

  it('shows errors[] from a 422 and keeps the dialog open', async () => {
    open({
      'POST /api/projects/muoi/script/apply': () =>
        json(
          {
            detail: 'JSON có 1 lỗi, chưa áp',
            errors: [{ code: 'K12', scene_index: null, field: 'scenes', message: 'hỏng bản gộp' }],
          },
          422,
        ),
    });
    const { user, dialog } = await toCheckStep();
    await user.click(within(dialog).getByRole('button', { name: 'Áp dụng 2 cảnh' }));
    expect(await within(dialog).findByText(/hỏng bản gộp/)).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Áp dụng 2 cảnh' })).toBeDisabled();
  });

  it('409 from a stale hash toasts and re-checks to get a fresh base_hash', async () => {
    let checks = 0;
    const mock = open({
      'POST /api/projects/muoi/script/check': () =>
        json(
          checkResult({
            base_hash: checks++ === 0 ? 'h1' : 'h9',
            counts: { json: 2, project: 3, after: 3 },
            diff: [{ scene_index: 0, field: 'punch', before: false, after: true }],
          }),
        ),
      'POST /api/projects/muoi/script/apply': () =>
        json({ detail: 'Project đã đổi sau lần kiểm, hãy kiểm lại' }, 409),
    });
    const { user, dialog } = await toCheckStep();
    await user.click(within(dialog).getByRole('button', { name: 'Áp dụng 2 cảnh' }));
    expect(await screen.findByText('Dự án đã đổi sau lần kiểm, đã kiểm lại.')).toBeInTheDocument();
    await waitFor(() => expect(bodiesTo(mock, '/script/check')).toHaveLength(2));
  });

  it('is locked while this project renders: Áp dụng disabled, no Hoàn tác offered', async () => {
    open();
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'bắt đầu dựng' }));
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const dialog = await paste('[{"punch":true}]');
    await user.click(within(dialog).getByRole('button', { name: 'Kiểm tra' }));
    await within(dialog).findByText('Cảnh 1');
    expect(within(dialog).getByRole('button', { name: 'Áp dụng 2 cảnh' })).toBeDisabled();
    expect(within(dialog).getByText('Đang dựng, đợi xong hoặc huỷ job rồi áp')).toBeInTheDocument();
    act(() => FakeEventSource.instances[0].emit('end', { status: 'done' }));
    await waitFor(() =>
      expect(within(dialog).getByRole('button', { name: 'Áp dụng 2 cảnh' })).toBeEnabled(),
    );
  });

  it('a 409 "đang dựng" from the server is shown as a toast, dialog stays', async () => {
    open({
      'POST /api/projects/muoi/script/apply': () =>
        json({ detail: 'Project đang được dựng, hãy đợi xong' }, 409),
    });
    const { user, dialog } = await toCheckStep();
    await user.click(within(dialog).getByRole('button', { name: 'Áp dụng 2 cảnh' }));
    expect((await screen.findAllByText(/đang được dựng/)).length).toBeGreaterThan(0);
    expect(screen.getByRole('dialog', { name: 'Dán JSON kịch bản' })).toBeInTheDocument();
  });
});
