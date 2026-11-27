import type { ActiveJob, StudioEngine } from '../api/types';

export const JOB_PROGRESS_THROTTLE_MS = 250;

export interface RenderJobProgressSnapshot {
  percent: number;
  step: string;
  stage: string;
  message: string;
  currentBeat: number | null;
  totalBeats: number | null;
  current?: number;
  total?: number;
  status?: string;
  phase?: string;
  data?: Record<string, unknown>;
  timings?: Record<string, unknown>;
}

export interface RenderJobProgressStore {
  getSnapshot: () => RenderJobProgressSnapshot;
  setSnapshot: (next: RenderJobProgressSnapshot, immediate?: boolean) => void;
  subscribe: (listener: () => void) => () => void;
}

export const EMPTY_PROGRESS_SNAPSHOT: RenderJobProgressSnapshot = {
  percent: 0,
  step: '',
  stage: '',
  message: '',
  currentBeat: null,
  totalBeats: null,
};

export function inferJobEngine(
  kind: ActiveJob['kind'] | string | null | undefined,
  explicitEngine?: StudioEngine | string | null,
): StudioEngine {
  if (
    explicitEngine === 'core' ||
    explicitEngine === 'postv' ||
    explicitEngine === 'chatting' ||
    explicitEngine === 'stickv'
  ) {
    return explicitEngine;
  }
  if (kind === 'stickv') return 'stickv';
  if (kind === 'postv_quick' || kind === 'postv_auto') return 'postv';
  if (kind === 'chatting_auto' || kind === 'chatting_render') return 'chatting';
  return 'core';
}

export function resolveJobRoute(
  engine: StudioEngine,
  kind: ActiveJob['kind'] | string | null | undefined,
  slug: string | null | undefined,
  explicitRoute?: string | null,
): string {
  if (explicitRoute && explicitRoute.startsWith('/')) {
    return explicitRoute;
  }
  const cleanSlug = (slug ?? '').trim();
  const encSlug = cleanSlug ? encodeURIComponent(cleanSlug) : '';
  if (engine === 'stickv') {
    return encSlug ? `/stickv?slug=${encSlug}` : '/stickv';
  }
  if (engine === 'chatting') {
    return encSlug ? `/chatting/${encSlug}` : '/chatting';
  }
  if (engine === 'postv') {
    if (kind === 'postv_quick' || !encSlug) return '/postv';
    return `/postv/${encSlug}/export`;
  }
  if ((kind === 'preview' || kind === 'final' || kind === 'render') && encSlug) {
    return `/p/${encSlug}/export`;
  }
  return encSlug ? `/core?slug=${encSlug}` : '/core';
}

function sameSnapshot(a: RenderJobProgressSnapshot, b: RenderJobProgressSnapshot): boolean {
  return (
    a.percent === b.percent &&
    a.step === b.step &&
    a.stage === b.stage &&
    a.message === b.message &&
    a.currentBeat === b.currentBeat &&
    a.totalBeats === b.totalBeats &&
    a.current === b.current &&
    a.total === b.total &&
    a.status === b.status &&
    a.phase === b.phase &&
    a.data === b.data &&
    a.timings === b.timings
  );
}

/**
 * Store tiến độ cô lập cho `useSyncExternalStore` + throttle 250ms,
 * tránh re-render toàn cây React khi SSE bắn nhiều gói tin mỗi giây.
 */
export function createRenderJobProgressStore(
  initial: RenderJobProgressSnapshot = EMPTY_PROGRESS_SNAPSHOT,
  throttleMs = JOB_PROGRESS_THROTTLE_MS,
): RenderJobProgressStore {
  let current = initial;
  let pending: RenderJobProgressSnapshot | null = null;
  let lastNotifyAt = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;
  const listeners = new Set<() => void>();

  const notify = (next: RenderJobProgressSnapshot) => {
    current = next;
    lastNotifyAt = Date.now();
    for (const listener of listeners) {
      listener();
    }
  };

  return {
    getSnapshot: () => current,
    setSnapshot: (next: RenderJobProgressSnapshot, immediate = false) => {
      if (sameSnapshot(current, next) && (pending === null || sameSnapshot(pending, next))) {
        return;
      }
      const stepChanged = next.step !== current.step || next.stage !== current.stage;
      const isBoundary =
        immediate || lastNotifyAt === 0 || stepChanged || next.percent === 0 || next.percent >= 100;
      const elapsed = Date.now() - lastNotifyAt;

      if (throttleMs <= 0 || isBoundary || elapsed >= throttleMs) {
        if (timer !== null) {
          clearTimeout(timer);
          timer = null;
        }
        pending = null;
        notify(next);
        return;
      }

      pending = next;
      if (timer === null) {
        const wait = Math.max(16, throttleMs - elapsed);
        timer = setTimeout(() => {
          timer = null;
          if (pending !== null && !sameSnapshot(current, pending)) {
            const snap = pending;
            pending = null;
            notify(snap);
          } else {
            pending = null;
          }
        }, wait);
      }
    },
    subscribe: (listener: () => void) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
        if (listeners.size === 0 && timer !== null) {
          clearTimeout(timer);
          timer = null;
        }
      };
    },
  };
}
