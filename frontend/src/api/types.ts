/** Kiểu dữ liệu của API (khớp backend/hbt/models.py). Chỉ số cảnh trong API tính từ 0. */

export type LineSize = 's' | 'm' | 'l' | 'xl';
export type CardPreset = 'top' | 'upper' | 'middle' | 'lower';

export interface CardLine {
  text: string;
  size: LineSize;
  /** "ink" | "primary" | "accent" hoặc #RRGGBB */
  color: string;
}

export interface Card {
  y: CardPreset | number;
  lines: CardLine[];
}

export interface Label {
  text: string;
  x: number;
  y: number;
  size: number;
  color: string;
  rot: number;
}

export interface Scene {
  image: string;
  card: Card;
  labels: Label[];
  voice: string;
  punch: boolean;
  caption_y: number | null;
}

export interface Theme {
  primary: string;
  accent: string;
}

/** Backend ghi gọn thành tên file khi không có `trim_end`. */
export type VoiceField = string | { file: string; trim_end?: number | null } | null;

export interface Music {
  file: string | null;
  start: number | null;
  credit: string;
}

export type Aligner = 'auto' | 'whisper' | 'silence';

/** Chi tiết căn chữ ghi trong meta.json (có khi aligner là whisper, hoặc khi Whisper phải bỏ). */
export interface AlignerInfo {
  model?: string;
  device?: 'cuda' | 'cpu';
  compute_type?: string;
  whisper_seconds?: number;
  match_ratio?: number;
  last_token_matched?: boolean;
  /** Các bậc Whisper đã bỏ qua trước khi có kết quả, kèm lý do. */
  skipped?: string[];
  /** Lý do Whisper không dùng được khi phải rơi về khoảng lặng. */
  whisper_error?: string;
}
export type Fps = 30 | 50 | 60;

export interface ProjectSettings {
  fps: number;
  captions: boolean;
  aligner: Aligner;
  sfx_on_punch: boolean;
  outro: boolean;
}

export interface Thumbnail {
  /** Cảnh làm nền, đếm từ 1. */
  scene: number;
  lines: string[];
  series: string;
  accent: string;
  /** Ảnh bìa riêng đã tải lên (`images/cover.<ext>`); trống = dùng ảnh của cảnh `scene`. */
  image?: string | null;
}

export interface BuildClean {
  before_bytes: number;
  after_bytes: number;
  freed_bytes: number;
  kept: string[];
  failed: number;
}

/** Loại dự án: video HBT (ảnh + giọng) hoặc PostV (bài mạng xã hội trên nền gameplay). */
export type ProjectKind = 'video' | 'postv';

export interface Project {
  version: 1;
  slug: string;
  title: string;
  series: string;
  theme: Theme;
  voice: VoiceField;
  music: Music | null;
  settings: ProjectSettings;
  scenes: Scene[];
  publish: { hook: string; hashtags: string[] };
  thumbnail: Thumbnail | null;
}

export interface RenderSummary {
  job_id: string;
  preview: boolean;
  fps: number | null;
  duration: number | null;
  /** null = bản dựng cũ không ghi (IMPLEMENT 13.B6). */
  render_seconds?: number | null;
  align_cached?: boolean | null;
  /** Số giây giọng bị cắt đuôi; null = không cắt hoặc bản dựng cũ không ghi. */
  trimmed_tail_seconds?: number | null;
  created_at: string;
  video: string | null;
}

export interface ProjectSummary {
  slug: string;
  title: string;
  updated_at: string;
  thumb: string | null;
  last_render: RenderSummary | null;
  /** Bản đẹp mới nhất (không phải xem nhanh), cùng dạng `last_render`. */
  last_final: RenderSummary | null;
  /** Bìa 9:16 của lần dựng gần nhất có bìa. */
  cover: string | null;
  error: string | null;
  kind: ProjectKind;
}

export interface RenderRecord extends RenderSummary {
  width: number | null;
  height: number | null;
  lufs: number | null;
  aligner: string | null;
  aligner_info?: AlignerInfo | null;
  trimmed_tail?: string | null;
  music_start: number | null;
  music_start_source: 'manual' | 'auto' | null;
  /** null = dựng cả video. */
  preview_seconds: number | null;
  /** Nhạc hiện tại của project có đúng là nhạc đã dùng cho lần xuất này. */
  music_matches_current: boolean;
  size: number;
  srt: string | null;
  publish: string | null;
  log: string | null;
  cover: string | null;
  youtube_cover: string | null;
}

export interface LintIssue {
  scene_index: number | null;
  field: string;
  category: string;
  level: 'info' | 'warn' | 'block';
  message: string;
  word: string | null;
  hint: string;
}

export interface LintResult {
  issues: LintIssue[];
  counts: { info: number; warn: number; block: number };
  blocked: boolean;
  problems: string[];
}

export interface MusicEntry {
  id: string;
  file: string;
  title: string;
  artist: string;
  source: string;
  url: string;
  license: string;
  moods: string[];
  bpm: number | null;
}

export type JobStatus = 'queued' | 'running' | 'done' | 'failed' | 'cancelled';

export interface JobOutput {
  video: string;
  srt: string | null;
  cover: string | null;
  youtube_cover: string | null;
  publish: string;
  log: string;
  fps: number;
  width: number;
  height: number;
  duration: number;
  lufs: number | null;
  preview_seconds: number | null;
  aligner: string;
  aligner_info?: AlignerInfo | null;
  /** Phần giọng đã cắt khỏi cuối file (IMPLEMENT 4d.4); null nếu không cắt. */
  trimmed_tail?: string | null;
  trimmed_tail_seconds?: number | null;
  seconds: number;
  warnings: string[];
}

export interface Job {
  id: string;
  project: string;
  status: JobStatus;
  progress: number;
  step: string;
  log_tail: string[];
  output: JobOutput | null;
  error: string | null;
  needs_confirmation: boolean;
  /** Phần giọng sẽ bị cắt, để nghe trước khi xác nhận (khi needs_confirmation). */
  cut_audio?: string | null;
  preview: boolean;
  preview_seconds: number | null;
}

/** Một dòng của `GET /jobs`: job đang chạy hoặc đang chờ. */
export interface ActiveJob {
  id: string;
  slug: string;
  kind: 'preview' | 'final';
  status: 'queued' | 'running';
  progress: number;
  step: string;
}

export interface RenderOptions {
  preview?: boolean;
  /** Xem nhanh chỉ dựng chừng này giây đầu; bỏ trống = cả video. */
  preview_seconds?: number;
  fps?: Fps;
  outro?: boolean;
  allow_long_trim?: boolean;
}

export interface AppSettings {
  default_fps: Fps;
  theme: Theme;
  whisper_model: 'auto' | 'small' | 'medium' | 'large-v3';
  whisper_timeout_seconds: number;
}

export interface SensitiveCategory {
  id: string;
  level: 'info' | 'warn' | 'block';
  words: string[];
  hint: string;
}

export interface SensitiveWords {
  categories: SensitiveCategory[];
}

export interface ProjectCreate {
  title: string;
  series: string;
  scene_count?: number;
  /** Bỏ trống = video HBT. */
  kind?: ProjectKind;
}

export interface PostvStats {
  views: number | null;
  likes: number | null;
  replies: number | null;
  reposts: number | null;
  shares: number | null;
}

export interface PostvComment extends PostvStats {
  id: string;
  handle: string;
  age: string;
  text: string;
  parent: string | null;
  picked: boolean;
}

export interface PostvSegment {
  role: 'hook' | 'post' | 'comment' | 'commentary';
  card: 'hook' | 'post' | 'comment' | 'none' | null;
  voice: string;
  ref: string | null;
}

/** Dự án PostV (docs/postv/IMPLEMENT-POSTV.md mục 3). Có `kind: "postv"`, không có `scenes`. */
export interface PostvProject {
  version: 1;
  kind: 'postv';
  slug: string;
  title: string;
  series: string;
  theme: Theme;
  source: { url: string; note: string; pasted_at: string | null };
  post: PostvStats & { handle: string; age: string; text: string; card_text: string | null };
  comments: PostvComment[];
  segments: PostvSegment[];
  template: 'story_cards' | 'fixed_card';
  /** Thẻ tiêu đề ở giây đầu; trống = lấy câu đầu của bài. */
  hook: { text: string; accent: string };
  background: {
    mode: 'auto' | 'manual';
    clip_ids: string[];
    seed: number;
    start_offset: number | null;
  };
  style: { caption: { preset: 'hbt' | 'sample'; highlight_color: string | null } };
  voice: {
    engine: 'vieneu' | 'file';
    voice_id: string | null;
    file: string | null;
    trim_end: number | null;
  };
  music: Music | null;
  settings: {
    fps: number;
    captions: boolean;
    aligner: 'auto' | 'whisper' | 'silence';
    outro: boolean;
    card_animation: 'smooth' | 'bounce';
    censor: { enabled: boolean; sfx: 'bleep'; blur_card: boolean; text: 'blur' | 'stars' };
  };
  publish: { hook: string; hashtags: string[] };
  thumbnail: Thumbnail | null;
}

export type AnyProject = Project | PostvProject;

/** Clip nền gameplay trong thư viện (`GET /backgrounds`). */
export interface BackgroundEntry {
  id: string;
  file: string;
  title: string;
  source: string;
  license: string;
  url: string;
  width: number;
  height: number;
  fps: number;
  duration: number;
  tags: string[];
}

export interface NewBackgroundInput {
  file: File;
  title: string;
  source: string;
  license: string;
  url?: string;
  tags?: string;
}

/** Kết quả `POST /postv/parse` (hàm thuần, không ghi gì). */
export interface PostvParseResult {
  guess: 'threads_text' | 'embed' | 'unknown';
  source_url: string | null;
  post: { handle: string; age: string; text: string } | null;
  comments: {
    id: string;
    handle: string;
    age: string;
    text: string;
    same_author: boolean;
    picked: boolean;
  }[];
  /** Dòng chỉ gồm số có thể là số liệu; `block` 0 = bài gốc, i ≥ 1 = bình luận thứ i. */
  hints: { block: number; raw: string; value: number | null }[];
  warnings: string[];
}

/** Kết quả `POST /projects/{slug}/postv/script/check`: chỉ nhắc, không chặn. */
export interface PostvCheck {
  seconds: number;
  chars: number;
  long: boolean;
  censored: number;
  segments: { index: number; role: string; chars: number; seconds: number }[];
  issues: { where: string; level: 'info' | 'warn'; message: string; word: string | null }[];
}

export function isPostv(p: AnyProject): p is PostvProject {
  return 'kind' in p && p.kind === 'postv';
}

export interface NewMusicInput {
  file: File;
  title: string;
  artist: string;
  source: string;
  license: string;
  url?: string;
  moods?: string;
  bpm?: number | null;
}

/** Khối JSON kịch bản (IMPLEMENT 13.B4). */
export type ScriptExtra = 'add' | 'trim';

export interface ScriptIssue {
  code: string;
  /** Chỉ số cảnh từ 0; `null` = áp cho cả video. */
  scene_index: number | null;
  field: string;
  message: string;
  /** K10: `block` = sẽ chặn xuất, `warn` = lưu ý. */
  level?: 'block' | 'warn';
}

export interface ScriptDiffItem {
  scene_index: number | null;
  field: string;
  before: unknown;
  after: unknown;
}

export interface ScriptCheck {
  ok: boolean;
  base_hash: string;
  counts: { json: number; project: number; after: number };
  errors: ScriptIssue[];
  warnings: ScriptIssue[];
  diff: ScriptDiffItem[];
  /** Chỉ số (từ 0) các cảnh đổi lời đọc, sẽ căn chữ lại. */
  realign_scenes: number[];
}

export interface ScriptApplied {
  project: Project;
  backup_id: string;
  base_hash: string;
}

export interface BackupEntry {
  id: string;
  created_at: string;
  reason: 'apply' | 'restore' | null;
}
