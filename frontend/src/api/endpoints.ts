import { apiGet, apiPostBlob, apiRequest } from './client';
import type {
  ActiveJob,
  ProjectVoice,
  VoiceList,
  AppSettings,
  BackupEntry,
  Job,
  LintResult,
  BuildClean,
  Thumbnail,
  MusicEntry,
  NewMusicInput,
  AnyProject,
  BackgroundEntry,
  NewBackgroundInput,
  PostvAutoOptions,
  PostvBackupRecord,
  PostvCheck,
  PostvParseResult,
  PostvPickData,
  PostvProject,
  PostvQuickAutoResponse,
  PostvQuickOptions,
  PostvScriptStyle,
  Project,
  ProjectCreate,
  ProjectSummary,
  RenderOptions,
  RenderRecord,
  Scene,
  DraftCheck,
  DraftDoc,
  HbtVoiceInfo,
  DraftCreated,
  MemeEntry,
  ScriptApplied,
  ScriptCheck,
  ScriptExtra,
  ScriptJsonCheckResult,
  SensitiveWords,
  Theme,
  ChatDoc,
  ChatProjectDetail,
  ChatProjectSummary,
  ChattingJobInfo,
  HbtCoreAssetsInfo,
  HbtCoreGeminiModel,
  HbtCoreRenderResponse,
  HbtCoreScript,
  AssetHubCategory,
  AssetHubItem,
} from './types';

const enc = encodeURIComponent;

/** URL của file trong workspace (đường dẫn tương đối so với workspace). */
export const fileUrl = (rel: string) =>
  rel.startsWith('/api/files/') ? rel : `/api/files/${rel.replace(/^\/+/, '')}`;

/** URL của file nằm trong thư mục project. */
export const projectFileUrl = (slug: string, rel: string) => fileUrl(`projects/${slug}/${rel}`);

export const api = {
  listProjects: () => apiGet<ProjectSummary[]>('/projects'),
  getChattingStatus: () =>
    apiGet<{
      gemini_configured: boolean;
      model_available: boolean;
      model_name: string;
      models?: { id: string; name: string }[];
      stickers: Record<string, number>;
      total_stickers: number;
    }>('/chatting/status'),
  listChattingProjects: () => apiGet<ChatProjectSummary[]>('/chatting/projects'),
  createChattingProject: (input: {
    input: string;
    platform: string;
    background: string;
    direct_script?: boolean;
    target_duration_s?: number | null;
    model?: string;
  }) => apiRequest<{ slug: string; job_id: string }>('POST', '/chatting', { json: input }),
  getChattingProject: (slug: string) => apiGet<ChatProjectDetail>(`/chatting/${enc(slug)}`),
  getChattingJob: (slug: string) => apiGet<ChattingJobInfo>(`/chatting/${enc(slug)}/job`),
  updateChattingProject: (slug: string, doc: ChatDoc) =>
    apiRequest<{ ok: boolean; doc: ChatDoc }>('PUT', `/chatting/${enc(slug)}`, { json: doc }),
  regenChattingProject: (slug: string) =>
    apiRequest<{ ok: boolean; doc: ChatDoc; timings: Record<string, unknown> }>(
      'POST',
      `/chatting/${enc(slug)}/regen`,
    ),
  renderChattingProject: (slug: string, preview: boolean) =>
    apiRequest<{ job_id: string; slug: string; preview: boolean }>(
      'POST',
      `/chatting/${enc(slug)}/render`,
      {
        json: { preview },
      },
    ),
  deleteChattingProject: (slug: string) =>
    apiRequest<{ ok: boolean }>('DELETE', `/chatting/${enc(slug)}`),
  createProject: (input: ProjectCreate) =>
    apiRequest<AnyProject>('POST', '/projects', { json: input }),
  getProject: (slug: string) => apiGet<Project>(`/projects/${enc(slug)}`),
  /** Đọc dự án của cả hai loại; dùng khi chưa biết `kind` (trang mở theo đường dẫn). */
  getAnyProject: (slug: string) => apiGet<AnyProject>(`/projects/${enc(slug)}`),
  savePostv: (slug: string, project: PostvProject) =>
    apiRequest<AnyProject>('PUT', `/projects/${enc(slug)}`, { json: project }),
  parsePostv: (text: string) =>
    apiRequest<PostvParseResult>('POST', '/postv/parse', { json: { text } }),
  fetchThreads: (url: string) =>
    apiRequest<PostvParseResult>('POST', '/postv/fetch-threads', { json: { url } }),
  unlockProject: (slug: string) =>
    apiRequest<{ ok: boolean; slug: string; unlocked: number }>(
      'POST',
      `/projects/${enc(slug)}/unlock`,
    ),
  openPostvFolder: (slug: string) =>
    apiRequest<{ ok: boolean; path: string }>('POST', `/postv/${enc(slug)}/open-folder`, {
      json: {},
    }),
  searchMemes: (q: string, count = 12) =>
    apiGet<MemeEntry[]>(`/memes/search?q=${enc(q)}&count=${count}`),
  listMemeLibrary: () => apiGet<MemeEntry[]>('/memes/library'),
  downloadMeme: (body: {
    meme_id: string;
    video_url: string;
    title: string;
    poster_url?: string;
    source?: string;
    license?: string;
  }) => apiRequest<MemeEntry>('POST', '/memes/download', { json: body }),
  deleteMeme: (memeId: string) => apiRequest<{ status: string }>('DELETE', `/memes/${enc(memeId)}`),
  postvCheck: (slug: string) =>
    apiRequest<PostvCheck>('POST', `/projects/${enc(slug)}/postv/script/check`, { json: {} }),
  saveProject: (slug: string, project: Project) =>
    apiRequest<Project>('PUT', `/projects/${enc(slug)}`, { json: project }),
  deleteProject: (slug: string) => apiRequest<void>('DELETE', `/projects/${enc(slug)}`),
  duplicateProject: (slug: string) =>
    apiRequest<AnyProject>('POST', `/projects/${enc(slug)}/duplicate`, { json: {} }),
  reorderScenes: (slug: string, order: number[]) =>
    apiRequest<Project>('POST', `/projects/${enc(slug)}/scenes/reorder`, { json: { order } }),
  deleteScene: (slug: string, sceneIndex: number) =>
    apiRequest<Project>('DELETE', `/projects/${enc(slug)}/scenes/${sceneIndex}`),

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

  /** Ảnh bìa 9:16 theo bản nháp (chưa lưu); giao diện tự cắt khung 3:4 và 3:2. */
  previewThumbnail: (slug: string, thumbnail: Thumbnail, signal?: AbortSignal) =>
    apiPostBlob(`/projects/${enc(slug)}/thumbnail/preview.jpg?w=360`, { thumbnail }, signal),
  cleanBuild: (slug: string) =>
    apiRequest<BuildClean>('POST', `/projects/${enc(slug)}/build/clean`),

  uploadAsset: (
    slug: string,
    kind: 'image' | 'cover' | 'voice' | 'music',
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

  /** Kiểm JSON nháp `hbt_draft` (chuỗi người dùng dán). Không ghi gì. */
  checkDraft: (draft: string) =>
    apiRequest<DraftCheck>('POST', '/gd2/draft/check', { json: { draft } }),
  /** Tạo dự án từ JSON nháp. 422 = còn lỗi (`body.errors`). */
  createDraft: (draft: string, title?: string) =>
    apiRequest<DraftCreated>('POST', '/gd2/draft/create', {
      json: { draft, title: title ?? null },
    }),
  /** Dự án có bản nháp GĐ2 không? Luôn 200 (không sinh 404 khi không có). */
  draftExists: (slug: string) => apiGet<{ exists: boolean }>(`/projects/${enc(slug)}/draft/exists`),
  getDraft: (slug: string) => apiGet<DraftDoc>(`/projects/${enc(slug)}/draft`),
  /** Duyệt ảnh (lưu dấu ảnh từng cảnh) hoặc bỏ duyệt. 422 khi còn cảnh chưa có ảnh. */
  setImagesApproved: (slug: string, approved: boolean) =>
    apiRequest<DraftDoc>('PUT', `/projects/${enc(slug)}/draft/images-approved`, {
      json: { approved },
    }),
  setScenePrompt: (slug: string, index: number, imagePrompt: string) =>
    apiRequest<DraftDoc>('PUT', `/projects/${enc(slug)}/draft/scenes/${index}/prompt`, {
      json: { image_prompt: imagePrompt },
    }),
  /** Kiểm khối JSON kịch bản (chuỗi người dùng dán). Không ghi gì. */
  checkScript: (slug: string, script: string, extra?: ScriptExtra) =>
    apiRequest<ScriptCheck>('POST', `/projects/${enc(slug)}/script/check`, {
      json: { script, extra: extra ?? null },
    }),
  /** Áp khối JSON: sao lưu rồi ghi. 409 = đang dựng hoặc `baseHash` lệch; 422 = còn lỗi. */
  applyScript: (slug: string, script: string, baseHash: string, extra?: ScriptExtra) =>
    apiRequest<ScriptApplied>('POST', `/projects/${enc(slug)}/script/apply`, {
      json: { script, extra: extra ?? null, base_hash: baseHash },
    }),
  listBackups: (slug: string) => apiGet<BackupEntry[]>(`/projects/${enc(slug)}/backups`),
  restoreBackup: (slug: string, backupId: string) =>
    apiRequest<ScriptApplied>('POST', `/projects/${enc(slug)}/backups/${enc(backupId)}/restore`),

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
  libraryMusicUrl: (id: string) => `/api/music/${enc(id)}/audio`,
  listBackgrounds: () => apiGet<BackgroundEntry[]>('/backgrounds'),
  addBackground: (input: NewBackgroundInput) => {
    const form = new FormData();
    form.set('file', input.file);
    for (const key of ['title', 'source', 'license', 'url', 'tags'] as const) {
      form.set(key, input[key] ?? '');
    }
    return apiRequest<BackgroundEntry>('POST', '/backgrounds', { form });
  },
  deleteBackground: (id: string) => apiRequest<void>('DELETE', `/backgrounds/${enc(id)}`),
  deletePostvVoice: (slug: string) =>
    apiRequest<void>('DELETE', `/projects/${enc(slug)}/postv/assets/voice`),
  deletePostvMusic: (slug: string) =>
    apiRequest<void>('DELETE', `/projects/${enc(slug)}/postv/assets/music`),
  deletePostvSource: (slug: string) =>
    apiRequest<void>('DELETE', `/projects/${enc(slug)}/postv/source`),
  getPostvStyles: () => apiGet<PostvScriptStyle[]>('/postv/styles'),
  startPostvAuto: (slug: string, options: PostvAutoOptions) =>
    apiRequest<{ job_id: string }>('POST', `/projects/${enc(slug)}/postv/auto`, { json: options }),
  checkPostvScriptJson: (slug: string, body: unknown) =>
    apiRequest<ScriptJsonCheckResult>('POST', `/projects/${enc(slug)}/postv/script-json/check`, {
      json: body,
    }),
  applyPostvScriptJson: (slug: string, body: unknown) =>
    apiRequest<{ ok: boolean; backup_id: string }>(
      'POST',
      `/projects/${enc(slug)}/postv/script-json/apply`,
      { json: body },
    ),
  listPostvBackups: (slug: string) =>
    apiGet<PostvBackupRecord[]>(`/projects/${enc(slug)}/postv/backups`),
  restorePostvBackup: (slug: string, backupId: string) =>
    apiRequest<{ ok: boolean }>(
      'POST',
      `/projects/${enc(slug)}/postv/backups/${enc(backupId)}/restore`,
    ),
  backgroundThumbUrl: (id: string) => `/api/backgrounds/${enc(id)}/thumb`,
  backgroundVideoUrl: (id: string) => `/api/backgrounds/${enc(id)}/video`,
  /** Ảnh thẻ PostV vẽ ở máy chủ từ dữ liệu đã lưu; `version` đổi sau mỗi lần lưu để tải lại ảnh. */
  postvCardUrl: (
    slug: string,
    opts: { kind: 'hook' | 'post' | 'comment'; ref?: string; w?: number; version?: number },
  ) => {
    const q = new URLSearchParams({ kind: opts.kind });
    if (opts.ref) q.set('ref', opts.ref);
    if (opts.w) q.set('w', String(opts.w));
    if (opts.version !== undefined) q.set('v', String(opts.version));
    return `/api/projects/${enc(slug)}/postv/card.png?${q}`;
  },
  /** Ảnh xem trước tĩnh 9:16 của PostV: nền + thẻ + phụ đề mẫu (PV6). */
  postvPreviewUrl: (
    slug: string,
    opts?: {
      kind?: 'hook' | 'post' | 'comment';
      ref?: string;
      w?: number;
      version?: number;
      t?: number;
    },
  ) => {
    const q = new URLSearchParams();
    if (opts?.kind) q.set('kind', opts.kind);
    if (opts?.ref) q.set('ref', opts.ref);
    if (opts?.w) q.set('w', String(opts.w));
    if (opts?.version !== undefined) q.set('v', String(opts.version));
    if (opts?.t !== undefined) q.set('t', String(opts.t));
    const s = q.toString();
    return `/api/projects/${enc(slug)}/postv/preview.png${s ? `?${s}` : ''}`;
  },
  /** URL tiếng bíp 1 kHz che từ (PV6). */
  postvBleepUrl: () => '/api/postv/bleep.wav',
  /** Xem trước ảnh bìa PostV (khung gameplay hoặc ảnh tải lên) (PV6). */
  previewPostvThumbnail: (slug: string, thumbnail?: Thumbnail, signal?: AbortSignal) =>
    apiPostBlob(`/projects/${enc(slug)}/postv/thumbnail/preview.jpg?w=360`, { thumbnail }, signal),
  attachLibraryMusic: (slug: string, id: string) =>
    apiRequest<AnyProject>('POST', `/projects/${enc(slug)}/music/from-library`, { json: { id } }),

  lint: (slug: string) => apiRequest<LintResult>('POST', `/projects/${enc(slug)}/lint`),
  startRender: (slug: string, options: RenderOptions) =>
    apiRequest<{ job_id: string }>('POST', `/projects/${enc(slug)}/render`, { json: options }),
  listVoices: () => apiGet<VoiceList>('/voices'),
  getProjectVoice: (slug: string) => apiGet<ProjectVoice>(`/projects/${enc(slug)}/voice`),
  synthesizeVoice: (slug: string) =>
    apiRequest<{ job_id: string }>('POST', `/projects/${enc(slug)}/voice/synthesize`),
  /** Giọng VieNeu của dự án HBT (luôn 200; `available=false` khi chưa cài VieNeu). */
  getHbtVoice: (slug: string) => apiGet<HbtVoiceInfo>(`/projects/${enc(slug)}/draft/voice`),
  /** Sinh giọng HBT như một job; bỏ `voiceId` = giọng đã nhớ. */
  synthesizeHbtVoice: (slug: string, voiceId?: string) =>
    apiRequest<{ job_id: string }>('POST', `/projects/${enc(slug)}/draft/voice`, {
      json: { voice_id: voiceId ?? null },
    }),
  getVoicePreference: () => apiGet<{ voice_id: string | null }>('/gd2/voice/preferences'),
  setVoicePreference: (voiceId: string | null) =>
    apiRequest<{ voice_id: string | null }>('PUT', '/gd2/voice/preferences', {
      json: { voice_id: voiceId },
    }),
  listActiveJobs: () => apiGet<ActiveJob[]>('/jobs'),
  getJob: (jobId: string) => apiGet<Job>(`/jobs/${enc(jobId)}`),
  cancelJob: (jobId: string) => apiRequest<Job>('POST', `/jobs/${enc(jobId)}/cancel`),
  startPostvQuick: (body: {
    url?: string;
    text?: string;
    options?: PostvQuickOptions;
    force_new?: boolean;
  }) => apiRequest<PostvQuickAutoResponse>('POST', '/postv/auto', { json: body }),
  retryPostvQuick: (jobId: string) =>
    apiRequest<{ job_id: string; project_slug: string; resumed_stage: string }>(
      'POST',
      `/postv/auto/${enc(jobId)}/retry`,
    ),
  getPostvPickData: (jobId: string) => apiGet<PostvPickData>(`/postv/auto/${enc(jobId)}/pick`),
  submitPostvPick: (jobId: string, commentIds: string[]) =>
    apiRequest<{ job_id: string; project_slug: string; status: string }>(
      'POST',
      `/postv/auto/${enc(jobId)}/pick`,
      { json: { comment_ids: commentIds } },
    ),
  getPostvSettings: () => apiGet<{ voice_id: string | null }>('/postv/settings'),
  savePostvSettings: (body: { voice_id: string }) =>
    apiRequest<{ ok: boolean; voice_id: string }>('POST', '/postv/settings', { json: body }),
  deletePostvProject: (slug: string) => apiRequest<void>('DELETE', `/postv/${enc(slug)}`),
  voiceSampleUrl: (voiceId: string) => `/api/voices/${encodeURIComponent(voiceId)}/sample`,
  deleteRender: (slug: string, jobId: string) =>
    apiRequest<void>('DELETE', `/projects/${enc(slug)}/renders/${enc(jobId)}`),
  listRenders: (slug: string) => apiGet<RenderRecord[]>(`/projects/${enc(slug)}/renders`),

  getAppSettings: () => apiGet<AppSettings>('/settings/app'),
  saveAppSettings: (settings: AppSettings) =>
    apiRequest<AppSettings>('PUT', '/settings/app', { json: settings }),
  getSensitiveWords: () => apiGet<SensitiveWords>('/settings/sensitive-words'),
  saveSensitiveWords: (words: SensitiveWords) =>
    apiRequest<SensitiveWords>('PUT', '/settings/sensitive-words', { json: words }),

  getHbtCoreModels: () =>
    apiGet<{ models: HbtCoreGeminiModel[]; default: string }>('/hbt/core/models'),
  getHbtCoreAssets: (slug?: string) =>
    apiGet<HbtCoreAssetsInfo>(`/hbt-core/assets${slug ? `?slug=${enc(slug)}` : ''}`),
  getProjectCoreScript: (slug: string) =>
    apiGet<{ slug: string; script: HbtCoreScript }>(`/projects/${enc(slug)}/core-script`),
  checkHbtCoreV1: (script: string | HbtCoreScript) =>
    apiRequest<{ ok: boolean; script: HbtCoreScript; segments_count: number }>(
      'POST',
      '/hbt-core/v1/check',
      { json: { script } },
    ),
  renderHbtCoreV1: (body: {
    script: string | HbtCoreScript;
    slug?: string | null;
    voice_id?: string | null;
    fps?: number;
    preview?: boolean;
  }) => apiRequest<HbtCoreRenderResponse>('POST', '/hbt-core/v1/render', { json: body }),
  promptHbtCoreV2: (body: {
    prompt: string;
    topic?: string | null;
    selectedModel?: string | null;
    model_name?: string | null;
    slug?: string | null;
    voice_id?: string | null;
    fps?: number;
    preview?: boolean;
    auto_render?: boolean;
  }) => apiRequest<HbtCoreRenderResponse>('POST', '/hbt-core/v2/prompt', { json: body }),

  listAssetHub: (category: AssetHubCategory) =>
    apiGet<{ category: AssetHubCategory; items: AssetHubItem[] }>(`/asset-hub/${enc(category)}`),
  uploadAssetHub: (category: AssetHubCategory, file: File) => {
    const form = new FormData();
    form.set('file', file);
    return apiRequest<{ ok: boolean; item: AssetHubItem }>('POST', `/asset-hub/${enc(category)}`, {
      form,
    });
  },
  deleteAssetHub: (category: AssetHubCategory, filename: string) =>
    apiRequest<{ ok: boolean; deleted: string }>(
      'DELETE',
      `/asset-hub/${enc(category)}/${enc(filename)}`,
    ),
};
