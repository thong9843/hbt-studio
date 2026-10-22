import { apiGet, apiPostBlob, apiRequest } from './client';
import type {
  AppSettings,
  Job,
  LintResult,
  MusicEntry,
  NewMusicInput,
  Project,
  ProjectCreate,
  ProjectSummary,
  RenderOptions,
  RenderRecord,
  Scene,
  SensitiveWords,
  Theme,
} from './types';

const enc = encodeURIComponent;

/** URL của file trong workspace (đường dẫn tương đối so với workspace). */
export const fileUrl = (rel: string) => `/api/files/${rel}`;

/** URL của file nằm trong thư mục project. */
export const projectFileUrl = (slug: string, rel: string) => fileUrl(`projects/${slug}/${rel}`);

export const api = {
  listProjects: () => apiGet<ProjectSummary[]>('/projects'),
  createProject: (input: ProjectCreate) =>
    apiRequest<Project>('POST', '/projects', { json: input }),
  getProject: (slug: string) => apiGet<Project>(`/projects/${enc(slug)}`),
  saveProject: (slug: string, project: Project) =>
    apiRequest<Project>('PUT', `/projects/${enc(slug)}`, { json: project }),
  deleteProject: (slug: string) => apiRequest<void>('DELETE', `/projects/${enc(slug)}`),
  duplicateProject: (slug: string) =>
    apiRequest<Project>('POST', `/projects/${enc(slug)}/duplicate`, { json: {} }),
  reorderScenes: (slug: string, order: number[]) =>
    apiRequest<Project>('POST', `/projects/${enc(slug)}/scenes/reorder`, { json: { order } }),

  /** Xem trước một cảnh bản nháp (chưa lưu). `sceneIndex` tính từ 0. */
  previewScene: (
    slug: string,
    sceneIndex: number,
    scene: Scene,
    theme: Theme,
    signal?: AbortSignal,
  ) =>
    apiPostBlob(
      `/projects/${enc(slug)}/scenes/${sceneIndex}/preview.png?w=360`,
      { scene, theme },
      signal,
    ),

  uploadAsset: (
    slug: string,
    kind: 'image' | 'voice' | 'music',
    file: File,
    sceneIndex?: number,
  ) => {
    const form = new FormData();
    form.set('kind', kind);
    form.set('file', file);
    if (sceneIndex !== undefined) form.set('scene_index', String(sceneIndex));
    return apiRequest<{ kind: string; path: string; project: Project }>(
      'POST',
      `/projects/${enc(slug)}/assets`,
      { form },
    );
  },

  listMusic: () => apiGet<MusicEntry[]>('/music'),
  addMusic: (input: NewMusicInput) => {
    const form = new FormData();
    form.set('file', input.file);
    for (const key of ['title', 'artist', 'source', 'license', 'url', 'moods'] as const) {
      form.set(key, input[key] ?? '');
    }
    if (input.bpm) form.set('bpm', String(input.bpm));
    return apiRequest<MusicEntry>('POST', '/music', { form });
  },
  libraryMusicUrl: (file: string) => `/api/library/music/${enc(file)}`,
  attachLibraryMusic: (slug: string, file: string) =>
    apiRequest<Project>('POST', `/projects/${enc(slug)}/music/from-library`, { json: { file } }),

  lint: (slug: string) => apiRequest<LintResult>('POST', `/projects/${enc(slug)}/lint`),
  startRender: (slug: string, options: RenderOptions) =>
    apiRequest<{ job_id: string }>('POST', `/projects/${enc(slug)}/render`, { json: options }),
  getJob: (jobId: string) => apiGet<Job>(`/jobs/${enc(jobId)}`),
  cancelJob: (jobId: string) => apiRequest<Job>('POST', `/jobs/${enc(jobId)}/cancel`),
  listRenders: (slug: string) => apiGet<RenderRecord[]>(`/projects/${enc(slug)}/renders`),

  getAppSettings: () => apiGet<AppSettings>('/settings/app'),
  saveAppSettings: (settings: AppSettings) =>
    apiRequest<AppSettings>('PUT', '/settings/app', { json: settings }),
  getSensitiveWords: () => apiGet<SensitiveWords>('/settings/sensitive-words'),
  saveSensitiveWords: (words: SensitiveWords) =>
    apiRequest<SensitiveWords>('PUT', '/settings/sensitive-words', { json: words }),
};
