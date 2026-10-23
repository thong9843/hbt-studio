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
export type Fps = 30 | 50 | 60;

export interface ProjectSettings {
  fps: number;
  captions: boolean;
  aligner: Aligner;
  sfx_on_punch: boolean;
  outro: boolean;
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
  thumbnail: unknown;
}

export interface RenderSummary {
  job_id: string;
  preview: boolean;
  fps: number | null;
  duration: number | null;
  created_at: string;
  video: string | null;
}

export interface ProjectSummary {
  slug: string;
  title: string;
  updated_at: string;
  thumb: string | null;
  last_render: RenderSummary | null;
  error: string | null;
}

export interface RenderRecord extends RenderSummary {
  width: number | null;
  height: number | null;
  lufs: number | null;
  aligner: string | null;
  music_start: number | null;
  music_start_source: 'manual' | 'auto' | null;
  size: number;
  srt: string | null;
  publish: string | null;
  log: string | null;
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
  publish: string;
  log: string;
  fps: number;
  width: number;
  height: number;
  duration: number;
  lufs: number;
  aligner: string;
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
  preview: boolean;
}

export interface RenderOptions {
  preview?: boolean;
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
