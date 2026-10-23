import { describe, expect, it } from 'vitest';
import type { Project } from '../api/types';
import {
  countProjectVoiceChars,
  countVoiceChars,
  voiceFile,
  voiceTrimEnd,
  withVoiceTrim,
} from './voice';

describe('countVoiceChars', () => {
  it('ignores | { } and collapses whitespace like the backend', () => {
    expect(countVoiceChars('Muỗi | thích  {một trăm}')).toBe('Muỗi thích một trăm'.length);
    expect(countVoiceChars('  ')).toBe(0);
  });

  it('joins scenes with a single space', () => {
    expect(countProjectVoiceChars([{ voice: 'ab' }, { voice: 'cd' }])).toBe(5);
  });
});

describe('voice field', () => {
  const base = { voice: 'voice.mp3' } as Project;

  it('reads both the short and the object form', () => {
    expect(voiceFile('a.mp3')).toBe('a.mp3');
    expect(voiceFile({ file: 'b.mp3', trim_end: 3 })).toBe('b.mp3');
    expect(voiceFile(null)).toBeNull();
    expect(voiceTrimEnd('a.mp3')).toBeNull();
    expect(voiceTrimEnd({ file: 'b.mp3', trim_end: 3 })).toBe(3);
  });

  it('writes trim_end and goes back to the short form when cleared', () => {
    const trimmed = withVoiceTrim(base, 12.5);
    expect(trimmed.voice).toEqual({ file: 'voice.mp3', trim_end: 12.5 });
    expect(withVoiceTrim(trimmed, null).voice).toBe('voice.mp3');
    expect(withVoiceTrim({ voice: null } as Project, 3).voice).toBeNull();
  });
});
