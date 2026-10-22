import type { Project, VoiceField } from '../api/types';

export const VOICE_CHAR_LIMIT = 750;

/** Số ký tự lời đọc theo cách backend đếm (IMPLEMENT.md 4d): bỏ `|`, `{`, `}`, gộp khoảng trắng. */
export function countVoiceChars(text: string): number {
  return text.replace(/[|{}]/g, '').replace(/\s+/g, ' ').trim().length;
}

/** Tổng ký tự toàn video: các cảnh nối bằng một dấu cách. */
export function countProjectVoiceChars(scenes: { voice: string }[]): number {
  return countVoiceChars(scenes.map((s) => s.voice).join(' '));
}

export function voiceFile(voice: VoiceField): string | null {
  if (!voice) return null;
  return typeof voice === 'string' ? voice : voice.file;
}

export function voiceTrimEnd(voice: VoiceField): number | null {
  return voice && typeof voice === 'object' ? (voice.trim_end ?? null) : null;
}

export function withVoiceTrim(project: Project, trimEnd: number | null): Project {
  const file = voiceFile(project.voice);
  if (!file) return project;
  return { ...project, voice: trimEnd === null ? file : { file, trim_end: trimEnd } };
}
