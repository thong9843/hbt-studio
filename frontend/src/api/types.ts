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
}

export interface BuildClean {
  before_bytes: number;
  after_bytes: number;
  freed_bytes: number;
  kept: string[];
  failed: number;
}

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
  scene_count: number;
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
