import { describe, expect, it } from 'vitest';

import { Placer, overlaps, placeStarLabel } from '../src/sky/labels';

const base = { offset: 15, width: 80, height: 17, limitRight: 800 };

describe('label placement', () => {
  it('puts the label right of the star by default', () => {
    expect(placeStarLabel({ ...base, sx: 100, sy: 100 }, new Placer([]))).toEqual({
      x: 115,
      y: 104,
    });
  });

  it('flips left at the right edge', () => {
    const p = placeStarLabel({ ...base, sx: 760, sy: 100 }, new Placer([]));
    expect(p?.x).toBe(760 - 15 - 80);
  });

  it('centres below when neither side fits', () => {
    const p = placeStarLabel({ ...base, sx: 50, sy: 100, limitRight: 120 }, new Placer([]));
    expect(p).toEqual({ x: 10, y: 100 + 15 + 18 });
  });

  it('never overlaps another label', () => {
    const placer = new Placer([]);
    expect(placeStarLabel({ ...base, sx: 100, sy: 100 }, placer)).not.toBeNull();
    expect(placeStarLabel({ ...base, sx: 104, sy: 102 }, placer)).toBeNull();
  });

  it('respects reserved rectangles such as the timeline', () => {
    const placer = new Placer([{ x: 0, y: 90, w: 800, h: 40 }]);
    expect(placeStarLabel({ ...base, sx: 100, sy: 100 }, placer)).toBeNull();
    expect(overlaps({ x: 0, y: 0, w: 10, h: 10 }, { x: 10, y: 0, w: 10, h: 10 })).toBe(false);
  });
});
