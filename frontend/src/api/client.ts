export class ApiError extends Error {
  readonly status: number;
  /** Thân JSON của lỗi (vd `errors[]` của script/apply); `null` khi không đọc được. */
  readonly body: unknown;

  constructor(status: number, message: string, body: unknown = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

type FetchFn = typeof fetch;

async function throwIfNotOk(res: Response): Promise<void> {
  if (res.ok) return;
  let detail = res.statusText;
  let body: unknown = null;
  try {
    body = await res.json();
    const d = (body as { detail?: unknown }).detail;
    if (typeof d === 'string') detail = d;
  } catch {
    // Thân lỗi không phải JSON — giữ statusText.
  }
  throw new ApiError(res.status, detail, body);
}

export async function apiRequest<T>(
  method: string,
  path: string,
  body?: { json?: unknown; form?: FormData },
  fetchFn: FetchFn = fetch,
): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  let payload: BodyInit | undefined;
  if (body?.form) {
    payload = body.form;
  } else if (body?.json !== undefined) {
    headers['Content-Type'] = 'application/json';
    payload = JSON.stringify(body.json);
  }
  const res = await fetchFn(`/api${path}`, { method, headers, body: payload });
  await throwIfNotOk(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const apiGet = <T>(path: string, fetchFn?: FetchFn) =>
  apiRequest<T>('GET', path, undefined, fetchFn);

/** POST gửi JSON, nhận về một file (ảnh PNG xem trước bản nháp). */
export async function apiPostBlob(
  path: string,
  json: unknown,
  signal?: AbortSignal,
  fetchFn: FetchFn = fetch,
): Promise<Blob> {
  const res = await fetchFn(`/api${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(json),
    signal,
  });
  await throwIfNotOk(res);
  return res.blob();
}

export async function fetchText(url: string, fetchFn: FetchFn = fetch): Promise<string> {
  const res = await fetchFn(url);
  await throwIfNotOk(res);
  return res.text();
}

export interface Health {
  ok: boolean;
  ffmpeg: boolean;
  whisper: boolean;
  gpu: boolean;
  /** Encoder/filter FFmpeg còn thiếu; ["ffmpeg"] nếu không chạy được FFmpeg. */
  missing: string[];
}

export const fetchHealth = (fetchFn?: FetchFn) => apiGet<Health>('/health', fetchFn);
