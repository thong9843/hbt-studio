export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export async function apiGet<T>(path: string, fetchFn: typeof fetch = fetch): Promise<T> {
  const res = await fetchFn(`/api${path}`, { headers: { Accept: 'application/json' } });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === 'string') detail = body.detail;
    } catch {
      // Thân lỗi không phải JSON — giữ statusText.
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export interface Health {
  ok: boolean;
  ffmpeg: boolean;
  whisper: boolean;
  gpu: boolean;
  /** Encoder/filter FFmpeg còn thiếu; ["ffmpeg"] nếu không chạy được FFmpeg. */
  missing: string[];
}

export const fetchHealth = (fetchFn?: typeof fetch) => apiGet<Health>('/health', fetchFn);
