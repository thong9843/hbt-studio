import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useAutosave } from './useAutosave';

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe('useAutosave', () => {
  it('saves once, 1 s after the last change, with the latest value', async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    const { result } = renderHook(() => useAutosave<string>(save));

    act(() => result.current.schedule('a'));
    await act(() => vi.advanceTimersByTimeAsync(600));
    act(() => result.current.schedule('ab'));
    expect(result.current.status).toBe('dirty');

    await act(() => vi.advanceTimersByTimeAsync(999));
    expect(save).not.toHaveBeenCalled();
    await act(() => vi.advanceTimersByTimeAsync(2));
    expect(save).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenCalledWith('ab');
    expect(result.current.status).toBe('saved');
  });

  it('flush saves immediately and resolves after the save finishes', async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    const { result } = renderHook(() => useAutosave<number>(save));
    act(() => result.current.schedule(7));
    await act(() => result.current.flush());
    expect(save).toHaveBeenCalledWith(7);
    expect(result.current.hasPending()).toBe(false);
    // Không còn gì chờ: một lần lưu nữa sau 1 s cũng không xảy ra.
    await act(() => vi.advanceTimersByTimeAsync(2000));
    expect(save).toHaveBeenCalledTimes(1);
  });

  it('reports an error, keeps the value, and retries on flush', async () => {
    const save = vi.fn().mockRejectedValueOnce(new Error('đĩa đầy')).mockResolvedValue(undefined);
    const { result } = renderHook(() => useAutosave<string>(save));
    act(() => result.current.schedule('x'));
    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(result.current.status).toBe('error');
    expect(result.current.error).toBe('đĩa đầy');
    expect(result.current.hasPending()).toBe(true);

    await act(() => result.current.flush());
    expect(save).toHaveBeenCalledTimes(2);
    expect(save).toHaveBeenLastCalledWith('x');
    expect(result.current.status).toBe('saved');
    expect(result.current.error).toBeNull();
  });

  it('runs saves one after another and ends on the newest value', async () => {
    const order: string[] = [];
    let release: () => void = () => {};
    const save = vi.fn(async (v: string) => {
      order.push(`start ${v}`);
      if (v === 'one') await new Promise<void>((r) => (release = r));
      order.push(`end ${v}`);
    });
    const { result } = renderHook(() => useAutosave<string>(save));
    act(() => result.current.schedule('one'));
    await act(() => vi.advanceTimersByTimeAsync(1000));
    act(() => result.current.schedule('two'));
    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(order).toEqual(['start one']);
    await act(async () => release());
    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(order).toEqual(['start one', 'end one', 'start two', 'end two']);
  });

  it('flushes what is pending when the component unmounts', async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    const { result, unmount } = renderHook(() => useAutosave<string>(save));
    act(() => result.current.schedule('last'));
    unmount();
    await vi.advanceTimersByTimeAsync(0);
    expect(save).toHaveBeenCalledWith('last');
  });
});
