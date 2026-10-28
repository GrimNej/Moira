// Label placement (§4.3.4): right of the star (clearing the ring), else left, else centred below.
// No overlap with another label or a reserved rectangle (timeline, zoom group, matches pill).

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export function overlaps(a: Rect, b: Rect): boolean {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}

export class Placer {
  readonly placed: Rect[];

  constructor(reserved: Rect[]) {
    this.placed = reserved.map((r) => ({ ...r }));
  }

  /** Reserve the rect if it is free; returns whether it was placed. */
  fits(r: Rect): boolean {
    for (const b of this.placed) if (overlaps(r, b)) return false;
    this.placed.push(r);
    return true;
  }
}

export interface StarLabel {
  sx: number;
  sy: number;
  offset: number; // ring clearance + 9 px
  width: number;
  height: number; // 17 for a title, 32 with the date line
  limitRight: number; // the canvas edge, or the open card's left edge
}

/** Where the label's text starts, or null when it cannot be placed. */
export function placeStarLabel(l: StarLabel, placer: Placer): { x: number; y: number } | null {
  let x = l.sx + l.offset;
  let y = l.sy + 4;
  if (x + l.width > l.limitRight) x = l.sx - l.offset - l.width;
  if (x < 10) {
    x = Math.min(Math.max(l.sx - l.width / 2, 10), l.limitRight - l.width);
    y = l.sy + l.offset + 18;
  }
  if (x + l.width > l.limitRight + 2) return null;
  if (!placer.fits({ x: x - 2, y: y - 13, w: l.width + 6, h: l.height })) return null;
  return { x, y };
}
