import { apiRequest } from './client';
import type {
  StickvAnimationMode,
  StickvAspect,
  StickvDomain,
  StickvProject,
  StickvTheme,
} from './types';

export interface GeminiModelOption {
  id: string;
  name: string;
}

export interface StickvListResponse {
  items: StickvProject[];
  gemini_models: Array<string | GeminiModelOption>;
  default_model: string;
  director_prompt?: string;
  poses?: string[];
  puppet_ready?: boolean;
}

export const stickvApi = {
  list: () => apiRequest<StickvListResponse>('GET', '/stickv'),

  get: (slug: string) =>
    apiRequest<{ project: StickvProject }>('GET', `/stickv/${encodeURIComponent(slug)}`),

  create: (body: {
    title: string;
    topic?: string;
    domain?: StickvDomain;
    animation_mode?: StickvAnimationMode;
    music_mood?: string;
    aspect?: StickvAspect;
    theme?: StickvTheme;
    target_minutes?: number;
    gemini_model?: string;
  }) => apiRequest<{ project: StickvProject }>('POST', '/stickv', { json: body }),

  generate: (body: {
    idea: string;
    topic?: string;
    domain?: StickvDomain;
    animation_mode?: StickvAnimationMode;
    music_mood?: string;
    aspect?: StickvAspect;
    theme?: StickvTheme;
    target_minutes?: number;
    model?: string;
    slug?: string;
  }) =>
    apiRequest<{ project: StickvProject; meta: Record<string, unknown> }>(
      'POST',
      '/stickv/generate',
      { json: body },
    ),

  save: (slug: string, project: StickvProject) =>
    apiRequest<{ project: StickvProject }>('PUT', `/stickv/${encodeURIComponent(slug)}`, {
      json: project,
    }),

  remove: (slug: string) =>
    apiRequest<{ ok: boolean }>('DELETE', `/stickv/${encodeURIComponent(slug)}`),

  uploadBeatMedia: (slug: string, beatId: string, file: File) => {
    const form = new FormData();
    form.append('file', file);
    return apiRequest<{ ok: boolean; media_path: string; project: StickvProject }>(
      'POST',
      `/stickv/${encodeURIComponent(slug)}/beats/${encodeURIComponent(beatId)}/media`,
      { form },
    );
  },

  render: (slug: string, preview: boolean) =>
    apiRequest<{ job_id: string; slug: string; preview: boolean }>(
      'POST',
      `/stickv/${encodeURIComponent(slug)}/render`,
      { json: { preview } },
    ),

  importJson: (body: {
    raw_json: string;
    topic?: string;
    domain?: StickvDomain;
    animation_mode?: StickvAnimationMode;
    music_mood?: string;
    aspect?: StickvAspect;
    theme?: StickvTheme;
  }) => apiRequest<{ project: StickvProject }>('POST', '/stickv/import-json', { json: body }),

  importScript: (body: {
    raw_text: string;
    title?: string;
    topic?: string;
    domain?: StickvDomain;
    animation_mode?: StickvAnimationMode;
    music_mood?: string;
    aspect?: StickvAspect;
    theme?: StickvTheme;
  }) => apiRequest<{ project: StickvProject }>('POST', '/stickv/import-script', { json: body }),

  searchIconify: (q: string) =>
    apiRequest<{ items: Array<{ id: string; prefix: string; name: string; png_url: string }> }>(
      'GET',
      `/stickv/iconify/search?q=${encodeURIComponent(q)}`,
    ),

  searchReferenceImages: (q: string, limit = 6) =>
    apiRequest<{
      items: Array<{
        id: string;
        title: string;
        url: string;
        thumb_url: string;
        width: number;
        height: number;
        source: string;
      }>;
    }>('GET', `/stickv/reference-images/search?q=${encodeURIComponent(q)}&limit=${limit}`),

  applyReferenceImage: (
    slug: string,
    beatId: string,
    body: { url: string; query?: string; caption?: string },
  ) =>
    apiRequest<{ ok: boolean; media_path: string; project: StickvProject }>(
      'POST',
      `/stickv/${encodeURIComponent(slug)}/beats/${encodeURIComponent(beatId)}/reference-image`,
      { json: body },
    ),
};
