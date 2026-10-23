import { describe, expect, it } from 'vitest';
import type { Card } from '../api/types';
import {
  CARD_Y_MAX,
  cardPositionKey,
  cardYFromSelection,
  clampCardY,
  newCardLine,
  nonEmptyLines,
  normalizeColor,
} from './card';

describe('card position', () => {
  it('maps card.y to the select value and back', () => {
    expect(cardPositionKey('upper')).toBe('upper');
    expect(cardPositionKey(420)).toBe('custom');
    expect(cardYFromSelection('lower', 'top')).toBe('lower');
    expect(cardYFromSelection('custom', 'top')).toBe(300);
    expect(cardYFromSelection('custom', 512)).toBe(512);
    expect(() => cardYFromSelection('bottom', 'top')).toThrow(RangeError);
  });

  it('clamps typed pixels to 0..1920 as integers', () => {
    expect(clampCardY('250.6')).toBe(251);
    expect(clampCardY('-5')).toBe(0);
    expect(clampCardY(99999)).toBe(CARD_Y_MAX);
    expect(clampCardY('abc')).toBe(0);
  });
});

describe('card lines and colors', () => {
  it('starts a new line the way the API expects', () => {
    expect(newCardLine()).toEqual({ text: '', size: 'm', color: 'ink' });
  });

  it('keeps named colors, upper-cases hex, rejects the rest', () => {
    expect(normalizeColor('primary')).toBe('primary');
    expect(normalizeColor('#ff8800')).toBe('#FF8800');
    expect(() => normalizeColor('red')).toThrow(RangeError);
    expect(() => normalizeColor('#fff')).toThrow(RangeError);
  });

  it('drops blank lines but keeps order', () => {
    const card: Card = {
      y: 'top',
      lines: [
        { text: 'A', size: 'l', color: 'ink' },
        { text: '  ', size: 'm', color: 'ink' },
        { text: 'B', size: 's', color: 'accent' },
      ],
    };
    expect(nonEmptyLines(card).map((l) => l.text)).toEqual(['A', 'B']);
  });
});
