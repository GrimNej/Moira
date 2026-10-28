// The star model built from the columnar sky payload, plus constellation lines (MST per hub).

import type { Kind, SkyHub, SkyPayload } from '../api/types';
import { FLAG } from '../api/types';
import { binOf, DAY } from './palette';
import { seeded } from './milkyway';

export interface Star {
  id: string;
  title: string;
  source: string;
  x: number;
  y: number;
  kind: Kind;
  hub: string;
  t: number;
  imp: number;
  flags: number;
  base: number;
  ph: number;
  sp: number;
  gl: number;
  bin: number;
  dc: number;
  earlier: boolean;
  bornT: number;
  created: number;
  unborn: boolean;
  // per-frame screen state
  _sx: number;
  _sy: number;
  _r: number;
  _a: number;
  _on: boolean;
}

export interface Hub extends SkyHub {
  stars: Star[];
  s: number;
  edges: [Star, Star, number][];
}

export interface Model {
  stars: Star[];
  byId: Map<string, Star>;
  hubs: Hub[];
  hubById: Map<string, Hub>;
  threads: [Star, Star][];
  tMin: number;
  now: number;
}

function hash(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return (h >>> 0) % 2147483646 || 1;
}

export function makeStar(
  p: {
    id: string;
    title: string;
    source: string;
    x: number;
    y: number;
    kind: Kind;
    hub: string;
    t: number;
    imp: number;
    flags: number;
  },
  now: number,
): Star {
  const rnd = seeded(hash(p.id));
  return {
    ...p,
    base: 1.45 + p.imp * 2.6,
    ph: rnd() * 6.283,
    sp: 0.45 + rnd() * 1.0,
    gl: 8 + rnd() * 70,
    bin: binOf((now - p.t) / DAY),
    dc: Math.hypot(p.x, p.y),
    earlier: (p.flags & (FLAG.earlier | FLAG.corrected)) !== 0,
    bornT: 0,
    created: 0,
    unborn: false,
    _sx: 0,
    _sy: 0,
    _r: 0,
    _a: 0,
    _on: false,
  };
}

/** Minimum spanning tree; edges longer than 3× the median are skipped (§4.3.4). */
export function mst<T extends { x: number; y: number }>(list: T[]): [T, T, number][] {
  const n = list.length;
  if (n < 2) return [];
  const inT = new Array<boolean>(n).fill(false);
  const d = new Array<number>(n).fill(Infinity);
  const p = new Array<number>(n).fill(-1);
  const E: [T, T, number][] = [];
  d[0] = 0;
  for (let k = 0; k < n; k++) {
    let u = -1;
    for (let i = 0; i < n; i++) if (!inT[i] && (u < 0 || d[i]! < d[u]!)) u = i;
    inT[u] = true;
    if (p[u]! >= 0) E.push([list[p[u]!]!, list[u]!, d[u]!]);
    for (let v = 0; v < n; v++) {
      if (inT[v]) continue;
      const dd = Math.hypot(list[u]!.x - list[v]!.x, list[u]!.y - list[v]!.y);
      if (dd < d[v]!) {
        d[v] = dd;
        p[v] = u;
      }
    }
  }
  const sorted = E.map((e) => e[2]).sort((a, b) => a - b);
  const med = sorted[Math.floor(sorted.length / 2)] ?? 0;
  return E.filter((e) => e[2] <= med * 3);
}

export function buildModel(payload: SkyPayload, now: number): Model {
  const s = payload.stars;
  const stars: Star[] = s.id.map((id, i) =>
    makeStar(
      {
        id,
        title: s.title?.[i] ?? '',
        source: s.source?.[i] ?? 'typed',
        x: s.x[i]!,
        y: s.y[i]!,
        kind: s.kind[i]!,
        hub: s.hub[i]!,
        t: s.t[i]!,
        imp: s.imp[i]!,
        flags: s.flags[i]!,
      },
      now,
    ),
  );
  const byId = new Map(stars.map((x) => [x.id, x]));
  const hubs: Hub[] = payload.hubs.map((h) => ({ ...h, stars: [], s: 60, edges: [] }));
  const hubById = new Map(hubs.map((h) => [h.id, h]));
  for (const st of stars) hubById.get(st.hub)?.stars.push(st);
  for (const h of hubs) {
    h.stars.sort((a, b) => a.t - b.t);
    let far = 40;
    for (const st of h.stars) far = Math.max(far, Math.hypot(st.x - h.x, st.y - h.y));
    h.s = far;
    h.edges = mst(h.stars);
  }
  const threads: [Star, Star][] = [];
  for (const [a, b] of payload.threads) {
    const A = byId.get(a);
    const B = byId.get(b);
    if (A && B) threads.push([A, B]);
  }
  const tMin = (stars.length ? Math.min(...stars.map((x) => x.t)) : now - 30 * DAY) - 3 * DAY;
  return { stars, byId, hubs, hubById, threads, tMin, now };
}
