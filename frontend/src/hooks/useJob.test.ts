import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { FakeEventSource, stubFetch } from '../test/fakes';
import { useJob } from './useJob';

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal('EventSource', FakeEventSource);
});
afterEach(() => vi.unstubAllGlobals());

const doneJob = {
  id: 'j1',
  status: 'done',
  progress: 100,
  step: 'Xong',
  output: { video: '/api/files/v.mp4' },
};

describe('useJob', () => {
  it('follows progress events and loads the finished job on `end`', async () => {
    stubFetch({ 'GET /api/jobs/j1': doneJob });
    const onFinished = vi.fn();
    const { result } = renderHook(() => useJob('j1', onFinished));
    const source = FakeEventSource.instances[0];
    expect(source.url).toBe('/api/jobs/j1/events');

    act(() => source.emit('progress', { progress: 40, step: 'Ghép cảnh', message: 'cảnh 2/8' }));
    expect(result.current.progress).toEqual({
      progress: 40,
      step: 'Ghép cảnh',
      message: 'cảnh 2/8',
    });

    act(() => source.emit('end', { status: 'done' }));
    await waitFor(() => expect(result.current.job?.status).toBe('done'));
    expect(onFinished).toHaveBeenCalledWith(expect.objectContaining({ id: 'j1' }));
    expect(source.readyState).toBe(FakeEventSource.CLOSED);
  });

  it('falls back to GET /jobs/{id} when the stream closes without `end`', async () => {
    stubFetch({ 'GET /api/jobs/j1': { ...doneJob, status: 'failed', error: 'hỏng' } });
    const { result } = renderHook(() => useJob('j1'));
    const source = FakeEventSource.instances[0];
    source.readyState = FakeEventSource.CLOSED;
    act(() => source.emit('error'));
    await waitFor(() => expect(result.current.job?.error).toBe('hỏng'));
  });

  it('does nothing without a job id and closes the stream on unmount', () => {
    const { unmount, rerender } = renderHook(({ id }) => useJob(id), {
      initialProps: { id: null as string | null },
    });
    expect(FakeEventSource.instances).toHaveLength(0);
    rerender({ id: 'j9' });
    const source = FakeEventSource.instances[0];
    unmount();
    expect(source.readyState).toBe(FakeEventSource.CLOSED);
  });
});
