import { describe, expect, it, vi } from 'vitest';
import { ApiError, apiGet, fetchHealth } from './client';

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

describe('apiGet', () => {
  it('prefixes /api and parses JSON', async () => {
    const fetchFn = vi.fn().mockResolvedValue(jsonResponse({ a: 1 }));
    await expect(apiGet('/x', fetchFn)).resolves.toEqual({ a: 1 });
    expect(fetchFn.mock.calls[0][0]).toBe('/api/x');
  });

  it('throws ApiError carrying {detail}', async () => {
    const fetchFn = vi.fn().mockResolvedValue(jsonResponse({ detail: 'Không tìm thấy' }, 404));
    const err = await apiGet('/x', fetchFn).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 404, message: 'Không tìm thấy' });
  });

  it('falls back to statusText when body is not JSON', async () => {
    const fetchFn = vi
      .fn()
      .mockResolvedValue(new Response('boom', { status: 500, statusText: 'Server Error' }));
    await expect(apiGet('/x', fetchFn)).rejects.toMatchObject({ message: 'Server Error' });
  });
});

describe('fetchHealth', () => {
  it('calls /api/health', async () => {
    const health = { ok: true, ffmpeg: true, whisper: false, gpu: false, missing: [] };
    const fetchFn = vi.fn().mockResolvedValue(jsonResponse(health));
    await expect(fetchHealth(fetchFn)).resolves.toEqual(health);
    expect(fetchFn.mock.calls[0][0]).toBe('/api/health');
  });
});
