import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useRenderJob } from '../hooks/renderJob';
import { FakeEventSource, stubFetch } from '../test/fakes';
import { RenderJobProvider } from './RenderJobProvider';

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal('EventSource', FakeEventSource);
});
afterEach(() => vi.unstubAllGlobals());

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={new QueryClient()}>
    <RenderJobProvider>{children}</RenderJobProvider>
  </QueryClientProvider>
);

const doneJob = { id: 'j1', project: 'muoi', status: 'done', progress: 100, step: 'Xong' };

describe('RenderJobProvider', () => {
  it('opens no stream while idle', () => {
    renderHook(() => useRenderJob(), { wrapper });
    expect(FakeEventSource.instances).toHaveLength(0);
  });

  it('opens one stream per job, follows progress and closes on end', async () => {
    const fetchMock = stubFetch({
      'POST /api/projects/muoi/render': { job_id: 'j1' },
      'GET /api/jobs/j1': doneJob,
    });
    const { result } = renderHook(() => useRenderJob(), { wrapper });

    await act(() => result.current.start('muoi', { preview: true, preview_seconds: 10 }, 30));
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(result.current.running).toBe(true);
    expect(result.current.slug).toBe('muoi');
    expect(result.current.estimateSeconds).toBe(30);

    const source = FakeEventSource.instances[0];
    act(() => source.emit('progress', { progress: 40, step: 'Ghép cảnh', message: '' }));
    expect(result.current.percent).toBe(40);
    expect(result.current.step).toBe('Ghép cảnh');

    act(() => source.emit('end', { status: 'done' }));
    await waitFor(() => expect(result.current.finished?.status).toBe('done'));
    expect(result.current.running).toBe(false);
    expect(source.readyState).toBe(FakeEventSource.CLOSED);
    // Không còn kết nối hay request nào sau khi xong.
    const calls = fetchMock.mock.calls.length;
    await new Promise((r) => setTimeout(r, 50));
    expect(fetchMock.mock.calls.length).toBe(calls);
    expect(FakeEventSource.instances).toHaveLength(1);
  });

  it('rethrows API errors (409) and stays idle', async () => {
    stubFetch({
      'POST /api/projects/muoi/render': () =>
        new Response(JSON.stringify({ detail: 'đang dựng' }), {
          status: 409,
          headers: { 'Content-Type': 'application/json' },
        }),
    });
    const { result } = renderHook(() => useRenderJob(), { wrapper });
    await expect(act(() => result.current.start('muoi', {}))).rejects.toThrow();
    expect(result.current.running).toBe(false);
    expect(FakeEventSource.instances).toHaveLength(0);
  });
});
