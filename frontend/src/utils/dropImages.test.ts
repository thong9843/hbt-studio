import { describe, expect, it } from 'vitest';
import { compareNatural, planImageDrop, sortFilesNatural } from './dropImages';

const file = (name: string) => new File(['x'], name, { type: 'image/png' });
const names = (files: File[]) => files.map((f) => f.name);
const scenes = (n: number, withImage: number[] = []) =>
  Array.from({ length: n }, (_, i) => ({ image: withImage.includes(i) ? `images/${i}.png` : '' }));

describe('natural file order', () => {
  it('puts 2 before 10 and ignores case', () => {
    expect(compareNatural('scene-2.png', 'scene-10.png')).toBeLessThan(0);
    expect(compareNatural('A1.png', 'a2.png')).toBeLessThan(0);
    expect(names(sortFilesNatural(['c10.png', 'c9.png', 'c1.png'].map(file)))).toEqual([
      'c1.png',
      'c9.png',
      'c10.png',
    ]);
  });

  it('is stable for names equal ignoring case', () => {
    expect(compareNatural('a.png', 'A.png')).not.toBe(0);
  });
});

describe('planImageDrop', () => {
  it('assigns sorted files from scene 1 with no overwrite on empty scenes', () => {
    const plan = planImageDrop(['b2.png', 'b10.png', 'b1.png'].map(file), scenes(8));
    expect(names(plan.existing)).toEqual(['b1.png', 'b2.png', 'b10.png']);
    expect(plan.overwrite).toEqual([]);
    expect(plan.extra).toEqual([]);
    expect(plan.dropped).toBe(0);
  });

  it('lists scenes that already have an image among the targets only', () => {
    const plan = planImageDrop(['1.png', '2.png'].map(file), scenes(8, [0, 1, 5]));
    expect(plan.overwrite).toEqual([0, 1]);
  });

  it('turns surplus files into new scenes', () => {
    const plan = planImageDrop(
      Array.from({ length: 10 }, (_, i) => file(`${i + 1}.png`)),
      scenes(8),
    );
    expect(plan.existing).toHaveLength(8);
    expect(names(plan.extra)).toEqual(['9.png', '10.png']);
    expect(plan.dropped).toBe(0);
  });

  it('cuts at 12 scenes and reports the rest as dropped', () => {
    const plan = planImageDrop(
      Array.from({ length: 15 }, (_, i) => file(`${i + 1}.png`)),
      scenes(8),
    );
    expect(plan.extra).toHaveLength(4);
    expect(plan.dropped).toBe(3);
    const full = planImageDrop([file('1.png')], scenes(12));
    expect(full.extra).toEqual([]);
    expect(
      planImageDrop([1, 2].map((n) => file(`${n}.png`)).concat(file('3.png')), scenes(3)).dropped,
    ).toBe(0);
    expect(
      planImageDrop(
        Array.from({ length: 14 }, (_, i) => file(`${i}.png`)),
        scenes(12),
      ).dropped,
    ).toBe(2);
  });

  it('leaves later scenes untouched when fewer files than scenes', () => {
    const plan = planImageDrop([file('1.png')], scenes(8));
    expect(plan.existing).toHaveLength(1);
    expect(plan.extra).toEqual([]);
  });
});
