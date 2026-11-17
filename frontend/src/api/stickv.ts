import { apiFetch } from './client';
import type { StickvAspect, StickvProject, StickvTheme } from './types';

export interface StickvListResponse {
  items: StickvProject[];
  gemini_models: string[];
  default_model: string;
}

export const stickvApi = {
  list: () => apiFetch<StickvListResponse>('/api/stickv'),

  get: (slug: string) =>
    apiFetch<{ project: StickvProject }>(`/api/stickv/${encodeURIComponent(slug)}`),

  create: (body: {
    title: string;
    topic?: string;
    aspect?: StickvAspect;
    theme?: StickvTheme;
    target_minutes?: number;
    gemini_model?: string;
  }) =>
    apiFetch<{ project: StickvProject }>('/api/stickv', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  generate: (body: {
    idea: string;
    topic?: string;
    aspect?: StickvAspect;
    theme?: StickvTheme;
    target_minutes?: number;
    model?: string;
    slug?: string;
  }) =>
    apiFetch<{ project: StickvProject; meta: Record<string, unknown> }>('/api/stickv/generate', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  save: (slug: string, project: StickvProject) =>
    apiFetch<{ project: StickvProject }>(`/api/stickv/${encodeURIComponent(slug)}`, {
      method: 'PUT',
      body: JSON.stringify(project),
    }),

  remove: (slug: string) =>
    apiFetch<{ ok: boolean }>(`/api/stickv/${encodeURIComponent(slug)}`, {
      method: 'DELETE',
    }),

  uploadBeatMedia: async (slug: string, beatId: string, file: File) => {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(
      `/api/stickv/${encodeURIComponent(slug)}/beats/${encodeURIComponent(beatId)}/media`,
      { method: 'POST', body: form },
    );
    if (!res.ok) {
      const err = (await res.json().catch(() => ({}))) as { detail?: string };
      throw new Error(err.detail || `Lỗi tải lên (${res.status})`);
    }
    return (await res.json()) as { ok: boolean; media_path: string; project: StickvProject };
  },

  render: (slug: string, preview: boolean) =>
    apiFetch<{ job_id: string; slug: string; preview: boolean }>(
      `/api/stickv/${encodeURIComponent(slug)}/render`,
      {
        method: 'POST',
        body: JSON.stringify({ preview }),
      },
    ),
};
