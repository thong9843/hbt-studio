import { describe, expect, it } from 'vitest';
import { sceneIndex, sceneNumber } from './scene';

describe('sceneNumber (chỉ số API từ 0 → số hiển thị từ 1)', () => {
  it('cộng thêm 1', () => {
    expect(sceneNumber(0)).toBe(1);
    expect(sceneNumber(7)).toBe(8);
    expect(sceneNumber(11)).toBe(12);
  });

  it('từ chối giá trị không hợp lệ', () => {
    expect(() => sceneNumber(-1)).toThrow(RangeError);
    expect(() => sceneNumber(1.5)).toThrow(RangeError);
    expect(() => sceneNumber(Number.NaN)).toThrow(RangeError);
  });
});

describe('sceneIndex (số người dùng từ 1 → chỉ số API từ 0)', () => {
  it('trừ đi 1', () => {
    expect(sceneIndex(1)).toBe(0);
    expect(sceneIndex(8)).toBe(7);
    expect(sceneIndex(12)).toBe(11);
  });

  it('từ chối 0, số âm và số lẻ (người dùng không có "cảnh 0")', () => {
    expect(() => sceneIndex(0)).toThrow(RangeError);
    expect(() => sceneIndex(-3)).toThrow(RangeError);
    expect(() => sceneIndex(2.5)).toThrow(RangeError);
  });
});

describe('hai chiều đổi luôn ngược nhau', () => {
  it('index → number → index', () => {
    for (let i = 0; i < 12; i++) expect(sceneIndex(sceneNumber(i))).toBe(i);
  });

  it('number → index → number', () => {
    for (let n = 1; n <= 12; n++) expect(sceneNumber(sceneIndex(n))).toBe(n);
  });

  it('không bao giờ trả về cùng một số cho hai đầu vào khác nhau', () => {
    const numbers = new Set(Array.from({ length: 12 }, (_, i) => sceneNumber(i)));
    expect(numbers.size).toBe(12);
  });
});
