import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useRenderJob } from '../hooks/renderJob';
import { getActiveStreamCount, resetActiveStreams } from '../hooks/useJob';
import { FakeEventSource, stubFetch } from '../test/fakes';
import { RenderJobProvider } from './RenderJobProvider';

beforeEach(() => {
  resetActiveStreams();
  FakeEventSource.instances = [];
  vi.stubGlobal('EventSource', FakeEventSource);
});
afterEach(() => {
  resetActiveStreams();
  vi.unstubAllGlobals();
});

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

    it('enforces single EventSource per jobId, throttles rapid progress bursts, and invalidates queries only on terminal end', async () => {
      stubFetch({
        'GET /api/jobs': [],
        'GET /api/jobs/sv-burst-1': {
          id: 'sv-burst-1',
          project: 'stickv-demo',
          slug: 'stickv-demo',
          kind: 'stickv',
          status: 'done',
          progress: 100,
          step: 'Ghép Outro & Hoàn tất',
        },
      });
      const qc = new QueryClient();
      const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
      const customWrapper = ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={qc}>
          <RenderJobProvider>{children}</RenderJobProvider>
        </QueryClientProvider>
      );

      const { result } = renderHook(() => useRenderJob(), { wrapper: customWrapper });

      act(() => {
        result.current.attachJob({
          jobId: 'sv-burst-1',
          slug: 'stickv-demo',
          kind: 'stickv',
          preview: false,
          progress: 2,
          step: 'Sinh giọng VieNeu-TTS',
          stage: 'Sinh giọng VieNeu-TTS',
        });
        // Gọi lặp attachJob cùng jobId nhiều lần (mô phỏng remount / click đúp)
        result.current.attachJob({
          jobId: 'sv-burst-1',
          slug: 'stickv-demo',
          kind: 'stickv',
          preview: false,
          progress: 5,
          step: 'Sinh giọng VieNeu-TTS',
        });
      });

      expect(FakeEventSource.instances).toHaveLength(1);
      expect(getActiveStreamCount()).toBe(1);
      expect(result.current.running).toBe(true);

      const es = FakeEventSource.instances[0];
      // Bắn dồn dập 20 sự kiện progress trong cùng 1 bước
      act(() => {
        for (let i = 10; i <= 80; i += 3.5) {
          es.emit('progress', {
            progress: Math.round(i),
            step: 'Dựng khung hình',
            stage: 'Dựng khung hình',
            message: `Frame ${i}`,
          });
        }
      });

      // Tuyệt đối không gọi invalidateQueries trong suốt quá trình nhận sự kiện progress
      expect(invalidateSpy).not.toHaveBeenCalled();

      // Khi kết thúc job -> chỉ invalidateQueries đúng 1 đợt duy nhất
      act(() => {
        es.emit('end', { status: 'done' });
      });
      await waitFor(() => expect(result.current.finished?.status).toBe('done'));
      expect(getActiveStreamCount()).toBe(0);
      expect(invalidateSpy).toHaveBeenCalled();
    });
  });
});
