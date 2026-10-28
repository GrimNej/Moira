// Picking: the star under a tap (hit area ≥ 16 px or 3× its radius), and nearest neighbours.

import type { Star } from './stars';

export function pick(stars: Star[], x: number, y: number): Star | null {
  let best: Star | null = null;
  let bd = 1e9;
  for (const s of stars) {
    if (!s._on) continue;
    const d = Math.hypot(s._sx - x, s._sy - y);
    const th = Math.max(16, s._r * 3);
    if (d < th && d < bd) {
      bd = d;
      best = s;
    }
  }
  return best;
}

export function nearest(pool: Star[], s: Star, k: number, visible: (o: Star) => boolean): Star[] {
  return pool
    .filter((o) => o !== s && visible(o))
    .map((o): [Star, number] => [o, Math.hypot(o.x - s.x, o.y - s.y)])
    .sort((a, b) => a[1] - b[1])
    .slice(0, k)
    .map((a) => a[0]);
}
