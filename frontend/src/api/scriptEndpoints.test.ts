import { afterEach, describe, expect, it, vi } from 'vitest';
import { stubFetch } from '../test/fakes';
import { json } from '../test/fakes';
import { api } from './endpoints';

afterEach(() => vi.unstubAllGlobals());

const bodyOf = (mock: ReturnType<typeof stubFetch>, i = 0) =>
  JSON.parse(String((mock.mock.calls[i][1] as RequestInit).body));

describe('script endpoints', () => {
  it('check posts the raw string and extra (null when omitted)', async () => {
    const mock = stubFetch({ 'POST /api/projects/muoi/script/check': { ok: true } });
    await api.checkScript('muoi', '[{"punch":true}]');
    expect(bodyOf(mock)).toEqual({ script: '[{"punch":true}]', extra: null });
    await api.checkScript('muoi', '[]', 'add');
    expect(bodyOf(mock, 1)).toEqual({ script: '[]', extra: 'add' });
  });

  it('apply sends base_hash', async () => {
    const mock = stubFetch({ 'POST /api/projects/muoi/script/apply': { backup_id: 'x' } });
    await api.applyScript('muoi', '[]', 'abc', 'trim');
    expect(bodyOf(mock)).toEqual({ script: '[]', extra: 'trim', base_hash: 'abc' });
  });

  it('apply 409 and 422 become ApiError with status (422 keeps errors[])', async () => {
    stubFetch({
      'POST /api/projects/muoi/script/apply': () =>
        json({ detail: 'JSON có 1 lỗi, chưa áp', errors: [{ code: 'K3' }] }, 422),
    });
    await expect(api.applyScript('muoi', '[]', 'h')).rejects.toMatchObject({
      status: 422,
      body: { errors: [{ code: 'K3' }] },
    });
    stubFetch({ 'POST /api/projects/muoi/script/apply': () => json({ detail: 'đang dựng' }, 409) });
    await expect(api.applyScript('muoi', '[]', 'h')).rejects.toMatchObject({ status: 409 });
  });

  it('lists backups and restores by id', async () => {
    const mock = stubFetch({
      'GET /api/projects/muoi/backups': [
        { id: '20261028-101500', created_at: 'x', reason: 'apply' },
      ],
      'POST /api/projects/muoi/backups/20261028-101500/restore': { backup_id: 'y' },
    });
    await expect(api.listBackups('muoi')).resolves.toHaveLength(1);
    await api.restoreBackup('muoi', '20261028-101500');
    expect(mock.mock.calls[1][0]).toBe('/api/projects/muoi/backups/20261028-101500/restore');
  });
});
