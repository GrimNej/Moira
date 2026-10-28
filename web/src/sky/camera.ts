// The camera (§4.3.5): flights are paths, not springs. They ease out of the current view, dip out
// a little on long trips, and land; any touch interrupts them from the live position.

import { clamp, easeIO, lerp } from './palette';

export const ZMIN = 0.22;
export const ZMAX = 60;

export interface View {
  x: number;
  y: number;
  z: number;
}

interface Flight {
  from: View;
  to: View;
  t0: number;
  dur: number;
  dip: number;
  mid?: () => void;
  done?: () => void;
  midDone: boolean;
}

export function flightDuration(screenDistance: number, zoomRatio: number): number {
  return clamp(650 + screenDistance * 0.35 + Math.abs(Math.log2(zoomRatio)) * 140, 700, 1600);
}

export class Camera {
  x = 0;
  y = 0;
  z = 1;
  vx = 0;
  vy = 0;
  flight: Flight | null = null;
  zoomA: { zt: number; ax: number; ay: number; wx: number; wy: number } | null = null;
  W = 0;
  H = 0;

  constructor(private readonly reduced: () => boolean) {}

  w2s(p: { x: number; y: number }): { x: number; y: number } {
    return { x: (p.x - this.x) * this.z + this.W / 2, y: (p.y - this.y) * this.z + this.H / 2 };
  }

  s2w(x: number, y: number): { x: number; y: number } {
    return { x: (x - this.W / 2) / this.z + this.x, y: (y - this.H / 2) / this.z + this.y };
  }

  cancelFlight(): void {
    const f = this.flight;
    if (!f) return;
    this.flight = null;
    if (!f.midDone && f.mid) {
      f.midDone = true;
      f.mid();
    }
  }

  flyTo(
    v: View,
    opts: { slow?: number; mid?: () => void; done?: () => void } = {},
    now = performance.now(),
  ): void {
    this.cancelFlight();
    const from = { x: this.x, y: this.y, z: this.z };
    const sd = Math.hypot(v.x - from.x, v.y - from.y) * Math.min(from.z, v.z);
    const dip = Math.min(1.4, Math.log2(1 + sd / (Math.min(this.W, this.H) * 0.8 || 1))) * 0.55;
    const dur = this.reduced() ? 0 : flightDuration(sd, v.z / from.z) * (opts.slow ?? 1);
    this.zoomA = null;
    this.vx = this.vy = 0;
    if (!dur) {
      this.x = v.x;
      this.y = v.y;
      this.z = v.z;
      opts.mid?.();
      opts.done?.();
      return;
    }
    this.flight = {
      from,
      to: v,
      t0: now,
      dur,
      dip,
      mid: opts.mid,
      done: opts.done,
      midDone: false,
    };
  }

  stepFlight(now: number): void {
    const f = this.flight;
    if (!f) return;
    const p = clamp((now - f.t0) / f.dur, 0, 1);
    const e = easeIO(p);
    this.x = lerp(f.from.x, f.to.x, e);
    this.y = lerp(f.from.y, f.to.y, e);
    this.z = Math.exp(
      lerp(Math.log(f.from.z), Math.log(f.to.z), e) - f.dip * Math.sin(Math.PI * e),
    );
    if (!f.midDone && p >= 0.62) {
      f.midDone = true;
      f.mid?.();
    }
    if (p >= 1) {
      this.flight = null;
      f.done?.();
    }
  }

  zoomBy(f: number, sx?: number, sy?: number): void {
    const ax = sx ?? this.W / 2;
    const ay = sy ?? this.H / 2;
    const zt = clamp((this.zoomA ? this.zoomA.zt : this.z) * f, ZMIN, ZMAX);
    this.cancelFlight();
    this.zoomA = {
      zt,
      ax,
      ay,
      wx: (ax - this.W / 2) / this.z + this.x,
      wy: (ay - this.H / 2) / this.z + this.y,
    };
  }

  stepZoom(): void {
    const a = this.zoomA;
    if (!a) return;
    const z = Math.exp(lerp(Math.log(this.z), Math.log(a.zt), this.reduced() ? 1 : 0.2));
    this.z = z;
    this.x = a.wx - (a.ax - this.W / 2) / z;
    this.y = a.wy - (a.ay - this.H / 2) / z;
    if (Math.abs(Math.log(z / a.zt)) < 0.002) {
      this.z = a.zt;
      this.x = a.wx - (a.ax - this.W / 2) / this.z;
      this.y = a.wy - (a.ay - this.H / 2) / this.z;
      this.zoomA = null;
    }
  }

  /** Inertia: velocity × 0.93 per frame. */
  stepInertia(): boolean {
    if (Math.abs(this.vx) <= 0.02 && Math.abs(this.vy) <= 0.02) return false;
    this.x -= this.vx / this.z;
    this.y -= this.vy / this.z;
    this.vx *= 0.93;
    this.vy *= 0.93;
    return true;
  }

  pan(dx: number, dy: number): void {
    this.x -= dx / this.z;
    this.y -= dy / this.z;
  }

  pinchTo(z: number, mx: number, my: number): void {
    const wx = (mx - this.W / 2) / this.z + this.x;
    const wy = (my - this.H / 2) / this.z + this.y;
    this.z = clamp(z, ZMIN, ZMAX);
    this.x = wx - (mx - this.W / 2) / this.z;
    this.y = wy - (my - this.H / 2) / this.z;
  }
}

/** The zoom that frames a star with its neighbours: clamp(min(w,h)·0.42 / maxDist, 2.2, 7). */
export function frameZoom(w: number, h: number, maxNeighbourDistance: number): number {
  return clamp((Math.min(w, h) * 0.42) / Math.max(60, maxNeighbourDistance), 2.2, 7);
}
