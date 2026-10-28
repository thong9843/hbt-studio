import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useRenderJob } from '../../hooks/renderJob';
import { FakeEventSource } from '../../test/fakes';
import { project } from '../../test/project';
import { setup } from './scriptTestKit';

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal('EventSource', FakeEventSource);
});
afterEach(() => vi.unstubAllGlobals());

const list = [
  { id: '20261028-101500-1', created_at: '2026-10-28T10:15:00Z', reason: 'restore' },
  { id: '20261028-101500', created_at: '2026-10-28T10:15:00Z', reason: 'apply' },
  { id: '20261027-090000', created_at: '2026-10-27T09:00:00Z', reason: null },
];

function Starter() {
  const job = useRenderJob();
  return (
    <button type="button" onClick={() => void job.start('muoi', {})}>
      bắt đầu dựng
    </button>
  );
}

async function openBackups(routes: Record<string, unknown> = {}) {
  const mock = setup(<Starter />, {
    'GET /api/projects/muoi/backups': list,
    'POST /api/projects/muoi/render': { job_id: 'j1' },
    ...routes,
  });
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Thêm thao tác' }));
  await user.click(screen.getByRole('menuitem', { name: 'Bản sao lưu' }));
  const dialog = await screen.findByRole('dialog', { name: 'Bản sao lưu' });
  return { mock, user, dialog };
}

describe('BackupsDialog (menu ⋯ → Bản sao lưu)', () => {
  it('lists backups with reason labels, including a null reason', async () => {
    const { dialog } = await openBackups();
    expect(await within(dialog).findAllByRole('button', { name: 'Khôi phục' })).toHaveLength(3);
    expect(within(dialog).getByText('Áp JSON')).toBeInTheDocument();
    expect(within(dialog).getByText('Khôi phục', { selector: 'p' })).toBeInTheDocument();
    expect(within(dialog).getByText('Không rõ')).toBeInTheDocument();
  });

  it('says so when there is no backup yet', async () => {
    const { dialog } = await openBackups({ 'GET /api/projects/muoi/backups': [] });
    expect(await within(dialog).findByText(/Chưa có bản sao lưu nào/)).toBeInTheDocument();
  });

  it('asks for confirmation, restores the chosen backup and swaps the project in', async () => {
    const restored = project({ title: 'Bản cũ' });
    const { mock, user, dialog } = await openBackups({
      'POST /api/projects/muoi/backups/20261028-101500/restore': {
        project: restored,
        backup_id: 'new',
        base_hash: 'h',
      },
    });
    const buttons = await within(dialog).findAllByRole('button', { name: 'Khôi phục' });
    await user.click(buttons[1]);
    const confirm = await screen.findByRole('alertdialog', { name: 'Khôi phục bản này?' });
    // Chưa gọi API trước khi xác nhận.
    expect(mock.mock.calls.some((c) => String(c[0]).includes('/restore'))).toBe(false);
    await user.click(within(confirm).getByRole('button', { name: 'Khôi phục' }));
    expect(await screen.findByText('Đã khôi phục')).toBeInTheDocument();
    expect(screen.getByLabelText('Tiêu đề')).toHaveValue('Bản cũ');
    expect(mock.mock.calls.some((c) => String(c[0]).endsWith('/20261028-101500/restore'))).toBe(
      true,
    );
  });

  it('cancelling the confirmation restores nothing', async () => {
    const { mock, user, dialog } = await openBackups();
    await user.click((await within(dialog).findAllByRole('button', { name: 'Khôi phục' }))[0]);
    const confirm = await screen.findByRole('alertdialog');
    await user.click(within(confirm).getByRole('button', { name: 'Huỷ' }));
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
    expect(mock.mock.calls.some((c) => String(c[0]).includes('/restore'))).toBe(false);
  });

  it('locks Khôi phục while this project renders', async () => {
    const { user } = await openBackups();
    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    await user.click(screen.getByRole('button', { name: 'bắt đầu dựng' }));
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    await user.click(screen.getByRole('button', { name: 'Thêm thao tác' }));
    await user.click(screen.getByRole('menuitem', { name: 'Bản sao lưu' }));
    const dialog = await screen.findByRole('dialog', { name: 'Bản sao lưu' });
    const buttons = await within(dialog).findAllByRole('button', { name: 'Khôi phục' });
    buttons.forEach((b) => expect(b).toBeDisabled());
    expect(within(dialog).getByText('Đang dựng, đợi xong hoặc huỷ job rồi khôi phục')).toBeTruthy();
    act(() => FakeEventSource.instances[0].emit('end', { status: 'done' }));
    await waitFor(() => expect(buttons[0]).toBeEnabled());
  });

  it('a 409 on restore shows a toast and keeps the project as it was', async () => {
    const { user, dialog } = await openBackups({
      'POST /api/projects/muoi/backups/20261027-090000/restore': () =>
        new Response(JSON.stringify({ detail: 'Project đang được dựng' }), {
          status: 409,
          headers: { 'Content-Type': 'application/json' },
        }),
    });
    const buttons = await within(dialog).findAllByRole('button', { name: 'Khôi phục' });
    await user.click(buttons[2]);
    await user.click(
      within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Khôi phục' }),
    );
    expect((await screen.findAllByText(/đang được dựng/)).length).toBeGreaterThan(0);
    expect(screen.getByLabelText('Tiêu đề')).toHaveValue('Muỗi');
  });
});
