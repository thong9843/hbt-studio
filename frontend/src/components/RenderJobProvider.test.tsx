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

  describe('nối lại job sau khi mở / tải lại trang', () => {
    const active = (id: string, status: string, kind = 'final') => ({
      id,
      slug: 'muoi',
      kind,
      status,
      progress: 35,
      step: 'Ghép cảnh',
    });

    it('asks GET /jobs once, reattaches SSE of the running job and never polls', async () => {
      const fetchMock = stubFetch({
        'GET /api/jobs': [active('q2', 'queued'), active('j1', 'running', 'preview')],
      });
      const { result } = renderHook(() => useRenderJob(), { wrapper });
      await waitFor(() => expect(result.current.running).toBe(true));
      expect(result.current.slug).toBe('muoi');
      expect(result.current.jobId).toBe('j1');
      expect(result.current.options.preview).toBe(true);
      expect(FakeEventSource.instances.map((i) => i.url)).toEqual(['/api/jobs/j1/events']);

      await new Promise((r) => setTimeout(r, 60));
      const listCalls = fetchMock.mock.calls.filter(([u]) => String(u) === '/api/jobs');
      expect(listCalls).toHaveLength(1);
    });

    it('stays idle when nothing is running or the request fails', async () => {
      stubFetch({ 'GET /api/jobs': [] });
      const idle = renderHook(() => useRenderJob(), { wrapper });
      await new Promise((r) => setTimeout(r, 40));
      expect(idle.result.current.running).toBe(false);
      expect(FakeEventSource.instances).toHaveLength(0);
      idle.unmount();

      stubFetch({}); // GET /api/jobs → 599
      const broken = renderHook(() => useRenderJob(), { wrapper });
      await new Promise((r) => setTimeout(r, 40));
      expect(broken.result.current.running).toBe(false);
      expect(FakeEventSource.instances).toHaveLength(0);
    });

    it('does not override a job the user starts before GET /jobs answers', async () => {
      let release: (rows: unknown) => void = () => undefined;
      const slow = new Promise((r) => (release = r));
      stubFetch({
        'GET /api/jobs': async () => Response.json(await slow),
        'POST /api/projects/muoi/render': { job_id: 'mine' },
      });
      const { result } = renderHook(() => useRenderJob(), { wrapper });
      await act(() => result.current.start('muoi', {}));
      release([active('old', 'running')]);
      await new Promise((r) => setTimeout(r, 40));
      expect(result.current.jobId).toBe('mine');
    });
  });
});
