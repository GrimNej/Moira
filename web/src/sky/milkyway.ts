// The Milky Way and the distant field (§4.3.4): a warm band of unresolved stars with darker dust
// lanes, and three parallax layers of field stars tiled every 2,400 units. Drawn, not decorated.

import { lerp } from './palette';

export const TILE = 2400;

/** A seeded Park–Miller generator: the same sky every time. */
export function seeded(seed: number): () => number {
  let s = seed;
  return () => {
    s = (s * 16807) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

export interface Blob {
  x: number;
  y: number;
  r: number;
  a: number;
}
export interface Dot {
  x: number;
  y: number;
  s: number;
  b: number;
}
export interface Layer {
  f: number;
  size: number;
  buckets: { style: string; pts: { x: number; y: number }[] }[];
}

export interface Field {
  bandBlobs: Blob[];
  lanes: Blob[];
  bandDust: Dot[];
  layers: Layer[];
}

const bandY = (x: number): number => lerp(780, -780, (x + 1300) / 2600);

export function makeField(seed = 20261026): Field {
  const rnd = seeded(seed);
  const bandBlobs: Blob[] = [];
  const lanes: Blob[] = [];
  const bandDust: Dot[] = [];
  for (let i = 0; i < 64; i++) {
    const x = lerp(-1500, 1500, rnd());
    const off = (rnd() - 0.5) * 240;
    bandBlobs.push({
      x: x + off * 0.514,
      y: bandY(x) + off * 0.857,
      r: 140 + rnd() * 240,
      a: 0.03 + rnd() * 0.03,
    });
  }
  for (let i = 0; i < 30; i++) {
    const x = lerp(-1400, 1400, rnd());
    const off = (rnd() - 0.5) * 80;
    lanes.push({
      x: x + off * 0.514,
      y: bandY(x) + off * 0.857,
      r: 40 + rnd() * 90,
      a: 0.45 + rnd() * 0.35,
    });
  }
  for (let i = 0; i < 2200; i++) {
    const x = lerp(-1500, 1500, rnd());
    const off = (rnd() + rnd() + rnd() - 1.5) * 240;
    bandDust.push({
      x: x + off * 0.514,
      y: bandY(x) + off * 0.857,
      s: rnd() < 0.86 ? 1 : 1.5,
      b: rnd() < 0.72 ? 0 : 1,
    });
  }
  const specs = [
    { n: 900, f: 0.05, size: 1, al: [0.08, 0.14, 0.2, 0.3] },
    { n: 340, f: 0.12, size: 1.2, al: [0.14, 0.24, 0.36, 0.5] },
    { n: 110, f: 0.24, size: 1.5, al: [0.2, 0.34, 0.5, 0.68] },
  ];
  const layers = specs.map((L) => {
    const buckets = L.al.map((a, i) => ({
      style: i % 2 ? `rgba(255,246,232,${a})` : `rgba(232,238,255,${a})`,
      pts: [] as { x: number; y: number }[],
    }));
    for (let i = 0; i < L.n; i++) {
      buckets[Math.floor(rnd() * buckets.length)]!.pts.push({ x: rnd() * TILE, y: rnd() * TILE });
    }
    return { f: L.f, size: L.size, buckets };
  });
  return { bandBlobs, lanes, bandDust, layers };
}
