import { describe, expect, it } from 'vitest';
import { insertVoiceMark } from './voiceEdit';

describe('insertVoiceMark', () => {
  it('inserts a | break at the caret', () => {
    expect(insertVoiceMark('Muỗi thích bạn', 5, 5, 'break')).toEqual({
      text: 'Muỗi |thích bạn',
      caret: 6,
    });
  });

  it('puts the caret inside {} right after the selected number', () => {
    const edit = insertVoiceMark('có 100 loài', 3, 6, 'number');
    expect(edit.text).toBe('có 100{} loài');
    expect(edit.caret).toBe(7);
  });

  it('clamps out-of-range positions', () => {
    expect(insertVoiceMark('ab', 99, 99, 'break')).toEqual({ text: 'ab|', caret: 3 });
    expect(insertVoiceMark('', 0, 0, 'number')).toEqual({ text: '{}', caret: 1 });
  });
});
