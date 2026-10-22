import { vi } from 'vitest';

export const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

export type Route = (url: string, init?: RequestInit) => Response | Promise<Response> | undefined;

/** Thay `fetch` toàn cục bằng bảng định tuyến theo "METHOD /đường-dẫn"; trả về mock để kiểm tra lời gọi. */
export function stubFetch(routes: Record<string, Route | unknown>) {
  const mock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const key = `${init?.method ?? 'GET'} ${url.replace(/\?.*$/, '')}`;
    const route = routes[key];
    if (route === undefined) return json({ detail: `chưa giả lập ${key}` }, 599);
    if (typeof route === 'function') return (route as Route)(url, init) ?? json({});
    return json(route);
  });
  vi.stubGlobal('fetch', mock);
  return mock;
}

/** EventSource giả: test tự phát sự kiện bằng `emit`. */
export class FakeEventSource {
  static instances: FakeEventSource[] = [];
  static CLOSED = 2;
  readyState = 1;
  listeners = new Map<string, ((ev: MessageEvent) => void)[]>();

  constructor(public url: string) {
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, fn: (ev: MessageEvent) => void) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), fn]);
  }

  close() {
    this.readyState = FakeEventSource.CLOSED;
  }

  emit(type: string, data?: unknown) {
    const ev = { data: JSON.stringify(data ?? {}) } as MessageEvent;
    this.listeners.get(type)?.forEach((fn) => fn(ev));
  }
}
