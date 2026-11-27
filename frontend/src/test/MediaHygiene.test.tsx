import { act, cleanup, render } from '@testing-library/react';
import { useRef } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { releaseVideoElement, useReleaseVideoOnUnmount } from '../hooks/useReleaseVideoOnUnmount';
import { ChattingHome } from '../pages/chatting/ChattingHome';
import { PostvQuickPage } from '../pages/PostvQuickPage';
import { stubFetch } from './fakes';
import { renderWithProviders } from './render';

function TestVideo({ src }: { src: string }) {
  const ref = useRef<HTMLVideoElement | null>(null);
  useReleaseVideoOnUnmount(ref, src);
  return <video ref={ref} src={src} data-testid="test-video" />;
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('Frontend Media Hygiene (INV-11)', () => {
  it('releaseVideoElement pauses, clears src, and calls load()', () => {
    const pauseSpy = vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
    const loadSpy = vi.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(() => {});

    const video = document.createElement('video');
    video.setAttribute('src', '/api/renders/demo.mp4');
    releaseVideoElement(video);

    expect(pauseSpy).toHaveBeenCalledTimes(1);
    expect(loadSpy).toHaveBeenCalledTimes(1);
    expect(video.getAttribute('src')).toBeNull();
  });

  it('useReleaseVideoOnUnmount releases buffer on unmount and key change', () => {
    const pauseSpy = vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
    const loadSpy = vi.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(() => {});

    const { getByTestId, rerender, unmount } = render(<TestVideo src="/api/video-a.mp4" />);
    const el = getByTestId('test-video') as HTMLVideoElement;
    expect(el.getAttribute('src')).toBe('/api/video-a.mp4');

    rerender(<TestVideo src="/api/video-b.mp4" />);
    expect(pauseSpy).toHaveBeenCalledTimes(1);
    expect(loadSpy).toHaveBeenCalledTimes(1);

    unmount();
    expect(pauseSpy).toHaveBeenCalledTimes(2);
    expect(loadSpy).toHaveBeenCalledTimes(2);
    expect(el.getAttribute('src')).toBeNull();
  });

  it('ChattingHome does not poll /api/chatting/status when idle', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let statusCalls = 0;

    stubFetch({
      'GET /api/chatting/status': () => {
        statusCalls += 1;
        return new Response(
          JSON.stringify({
            gemini_configured: true,
            model_available: true,
            model_name: 'gemini-3.1-flash-lite',
            stickers: {},
            total_stickers: 0,
          }),
          { headers: { 'Content-Type': 'application/json' } },
        );
      },
      'GET /api/chatting/projects': [],
    });

    renderWithProviders(<ChattingHome />, '/chatting');
    await act(async () => {
      await Promise.resolve();
      await vi.advanceTimersByTimeAsync(500);
    });
    expect(statusCalls).toBe(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_000);
    });
    expect(statusCalls).toBe(1);
  });

  it('PostvQuickPage does not poll /api/jobs every 3s when idle', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let jobListCalls = 0;

    stubFetch({
      'GET /api/jobs': () => {
        jobListCalls += 1;
        return new Response(JSON.stringify([]), {
          headers: { 'Content-Type': 'application/json' },
        });
      },
      'GET /api/projects': [],
      'GET /api/voices': { ok: true, provider: 'vieneu', voices: [] },
      'GET /api/gd2/voice/preferences': { voice_id: 'adam-bua' },
      'GET /api/music': [],
    });

    renderWithProviders(<PostvQuickPage />, '/postv');
    await act(async () => {
      await Promise.resolve();
      await vi.advanceTimersByTimeAsync(500);
    });
    const baselineCalls = jobListCalls;
    expect(baselineCalls).toBeGreaterThanOrEqual(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(jobListCalls).toBe(baselineCalls);
  });
});
