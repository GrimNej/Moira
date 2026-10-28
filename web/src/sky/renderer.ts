// The sky engine (§4.3.4–4.3.5): one class that owns the canvas, the camera, the frame loop and
// the pointer. Components talk to it through a small API; it calls back on select and tap.

import type { SkyPayload } from '../api/types';
import { Camera, frameZoom, ZMIN } from './camera';
import type { Comet, Flare, Search } from './effects';
import { COMET_MS, FLARE_MS, PULSE_MS, RIPPLE_MS } from './effects';
import { Placer, placeStarLabel, type Rect } from './labels';
import { Loop } from './loop';
import { makeField, TILE, type Field } from './milkyway';
import {
  clamp,
  DAY,
  DISPLAY_FONT,
  easeIO,
  easeOut,
  lerp,
  smooth,
  THREAD,
  UI_FONT,
} from './palette';
import { nearest, pick } from './picking';
import { sprites, type Sprites } from './sprites';
import { buildModel, type Model, type Star } from './stars';

export interface Region {
  l: number;
  r: number;
  t: number;
  b: number;
  w: number;
  h: number;
  cx: number;
  cy: number;
}

export interface Layout {
  /** Rects (canvas coordinates) labels must avoid: timeline, zoom group, matches pill. */
  reserved(): Rect[];
  /** The part of the window not covered by UI. */
  region(withCard: boolean): Region;
  isNarrow(): boolean;
  /** Left edge of the open card in canvas coordinates (desktop), or null. */
  cardLeft(): number | null;
  titleOf(id: string): string | undefined;
  subOf(s: Star): string;
}

export interface Callbacks {
  onSelect(id: string | null): void;
  onMid(id: string): void;
  onEmptyTap(): void;
  onLanded?(id: string): void;
}

const reduced = (): boolean =>
  typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;

export class SkyEngine {
  readonly cam = new Camera(reduced);
  private readonly ctx: CanvasRenderingContext2D;
  private readonly sp: Sprites;
  private readonly field: Field;
  private readonly loop: Loop;
  model: Model | null = null;
  private dpr = 1;
  private origin = { left: 0, top: 0 };
  sel: Star | null = null;
  private selT0 = 0;
  private selNear = new Set<string>();
  private focusMix = 0;
  hover: Star | null = null;
  search: Search | null = null;
  private searchMix = 0;
  private flares: Flare[] = [];
  private comet: Comet | null = null;
  private introT0 = 0;
  private introOn = true;
  timeT = Infinity;
  playing = false;
  private playT0 = 0;
  private playV0 = 0;
  onPlayTick: ((v: number) => void) | null = null;
  titles = new Map<string, string>();
  private ptrs = new Map<number, { x: number; y: number }>();
  private drag: {
    x: number;
    y: number;
    t: number;
    moved: number;
    hist: { t: number; dx: number; dy: number }[];
  } | null = null;
  private pinch: { d: number; mx: number | null; my: number | null } | null = null;
  private lastTap = 0;

  constructor(
    readonly canvas: HTMLCanvasElement,
    readonly layout: Layout,
    readonly cb: Callbacks,
  ) {
    this.ctx = canvas.getContext('2d')!;
    this.sp = sprites();
    this.field = makeField();
    this.loop = new Loop(
      (now) => this.frame(now),
      () => reduced(),
    );
    this.bind();
  }

  // ---------------------------------------------------------------- data

  setData(payload: SkyPayload, now: number, intro = false): void {
    const keep = this.sel?.id;
    const born = new Map((this.model?.stars ?? []).map((s) => [s.id, s]));
    this.model = buildModel(payload, now);
    for (const s of this.model.stars) {
      const old = born.get(s.id);
      if (old) {
        s.bornT = old.bornT;
        s.created = old.created;
      }
    }
    if (keep) this.sel = this.model.byId.get(keep) ?? null;
    if (intro) {
      this.introT0 = performance.now();
      this.introOn = !reduced();
      const v = this.fitView();
      if (reduced()) Object.assign(this.cam, v);
      else {
        this.cam.x = v.x + 60;
        this.cam.y = v.y + 30;
        this.cam.z = v.z * 0.78;
        this.cam.flyTo(v, { slow: 1.6 });
      }
    }
    this.wake();
  }

  get stars(): Star[] {
    return this.model?.stars ?? [];
  }

  visible = (s: Star): boolean => !s.unborn && (this.timeT === Infinity || s.t <= this.timeT);

  // ---------------------------------------------------------------- layout

  resize(): void {
    this.dpr = Math.min(2, window.devicePixelRatio || 1);
    const r = this.canvas.getBoundingClientRect();
    this.origin = { left: r.left, top: r.top };
    this.cam.W = r.width;
    this.cam.H = r.height;
    this.canvas.width = Math.round(r.width * this.dpr);
    this.canvas.height = Math.round(r.height * this.dpr);
    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    this.wake();
  }

  fitView(all = false): { x: number; y: number; z: number } {
    let x0 = 1e9,
      y0 = 1e9,
      x1 = -1e9,
      y1 = -1e9;
    for (const s of this.stars) {
      if (!all && !this.visible(s)) continue;
      x0 = Math.min(x0, s.x);
      x1 = Math.max(x1, s.x);
      y0 = Math.min(y0, s.y);
      y1 = Math.max(y1, s.y);
    }
    if (x0 > x1) {
      x0 = -400;
      x1 = 400;
      y0 = -300;
      y1 = 300;
    }
    const R = this.layout.region(false);
    const W = this.cam.W,
      H = this.cam.H;
    const z = clamp(
      Math.min((R.w - 40) / (x1 - x0 + 200), (R.h - 20) / (y1 - y0 + 200)) *
        (this.layout.isNarrow() ? 1.6 : 1),
      ZMIN,
      3,
    );
    const cx = (x0 + x1) / 2,
      cy = (y0 + y1) / 2;
    return { x: cx - (R.cx - W / 2) / z, y: cy - (R.cy - H / 2) / z, z };
  }

  fit(): void {
    this.cam.flyTo(this.fitView());
    this.wake();
  }

  zoomBy(f: number): void {
    this.cam.zoomBy(f);
    this.wake();
  }

  screenOf(id: string): { x: number; y: number } | null {
    const s = this.model?.byId.get(id);
    if (!s) return null;
    const p = this.cam.w2s(s);
    return { x: p.x + this.origin.left, y: p.y + this.origin.top };
  }

  // ---------------------------------------------------------------- selection

  neighbours(s: Star, k: number): Star[] {
    const hub = this.model?.hubById.get(s.hub);
    return nearest(hub ? hub.stars : this.stars, s, k, this.visible);
  }

  select(id: string, opts: { z?: number } = {}): boolean {
    const s = this.model?.byId.get(id);
    if (!s) return false;
    if (!this.visible(s)) this.setTime(1000);
    const wasOpen = this.sel !== null;
    this.sel = s;
    this.selT0 = performance.now();
    this.selNear = new Set(this.neighbours(s, 4).map((o) => o.id));
    for (const [a, b] of this.model!.threads) {
      if (a === s) this.selNear.add(b.id);
      if (b === s) this.selNear.add(a.id);
    }
    this.cb.onSelect(id);
    const R = this.layout.region(true);
    let md = 60;
    for (const nid of this.selNear) {
      const o = this.model!.byId.get(nid);
      if (o) md = Math.max(md, Math.hypot(o.x - s.x, o.y - s.y));
    }
    const z = opts.z ?? frameZoom(R.w, R.h, md);
    const W = this.cam.W,
      H = this.cam.H;
    this.cam.flyTo(
      { x: s.x - (R.cx - W / 2) / z, y: s.y - (R.cy - H / 2) / z, z },
      {
        mid: () => {
          if (!wasOpen && this.sel === s) this.cb.onMid(id);
        },
      },
    );
    this.wake();
    return true;
  }

  deselect(): void {
    if (!this.sel) return;
    this.sel = null;
    this.selNear = new Set();
    this.cb.onSelect(null);
    this.wake();
  }

  /** The answer glide (§4.3.5): the camera moves to the best match without opening the card. */
  glideTo(id: string): void {
    const s = this.model?.byId.get(id);
    if (!s) return;
    const R = this.layout.region(false);
    const z = clamp(Math.max(this.cam.z, 2.4), ZMIN, 4.5);
    const W = this.cam.W,
      H = this.cam.H;
    this.cam.flyTo({ x: s.x - (R.cx - W / 2) / z, y: s.y - (R.cy - H / 2) / z, z }, { slow: 1.15 });
    this.wake();
  }

  // ---------------------------------------------------------------- search

  light(ids: string[], top: string | null): void {
    const set = new Set(ids);
    const dist = new Map<string, number>();
    for (const s of this.stars) {
      const p = this.cam.w2s(s);
      dist.set(s.id, Math.hypot(p.x - this.cam.W / 2, p.y - this.cam.H / 2));
    }
    this.search = {
      set,
      top: top ? (this.model?.byId.get(top) ?? null) : null,
      t0: performance.now(),
      dist,
    };
    this.wake();
  }

  clearLight(): void {
    this.search = null;
    this.wake();
  }

  // ---------------------------------------------------------------- time

  tOf(v: number): number {
    const m = this.model;
    if (!m) return Date.now();
    return m.tMin + ((m.now - m.tMin) * v) / 1000;
  }

  setTime(v: number): void {
    this.timeT = v >= 999.5 ? Infinity : this.tOf(clamp(v, 0, 1000));
    if (this.sel && !this.visible(this.sel)) this.deselect();
    this.wake();
  }

  play(from: number): void {
    this.playing = true;
    this.playT0 = performance.now();
    this.playV0 = from >= 999.5 ? 0 : from;
    this.clearLight();
    this.deselect();
    const v = this.fitView(true);
    this.cam.flyTo({ x: v.x, y: v.y, z: v.z * 0.95 }, { slow: 1.2 });
    this.wake();
  }

  stop(): void {
    this.playing = false;
  }

  countVisible(): number {
    return this.stars.filter(this.visible).length;
  }

  // ---------------------------------------------------------------- new stars

  /** A blue-white comet arcs from the composer to the star's real position (§4.3.5). */
  cometTo(id: string, from: { x: number; y: number }, onLand?: () => void): void {
    const s = this.model?.byId.get(id);
    if (!s) return;
    s.unborn = true;
    s.created = performance.now();
    const z = clamp(Math.max(this.cam.z, 2.2), ZMIN, 5);
    const R = this.layout.region(false);
    const W = this.cam.W,
      H = this.cam.H;
    this.cam.flyTo({ x: s.x - (R.cx - W / 2) / z, y: s.y - (R.cy - H / 2) / z, z });
    this.comet = {
      s,
      t0: performance.now() + (reduced() ? 0 : 240),
      dur: reduced() ? 1 : COMET_MS,
      fx: from.x - this.origin.left,
      fy: from.y - this.origin.top,
      trail: [],
      onLand,
    };
    this.wake();
  }

  // ---------------------------------------------------------------- input

  private loc(e: PointerEvent | WheelEvent): { x: number; y: number } {
    const r = this.canvas.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  }

  private bind(): void {
    const c = this.canvas;
    c.addEventListener('pointerdown', (e) => {
      c.setPointerCapture(e.pointerId);
      const p = this.loc(e);
      this.ptrs.set(e.pointerId, p);
      this.cam.cancelFlight();
      this.cam.zoomA = null;
      if (this.ptrs.size === 1) {
        this.drag = { x: p.x, y: p.y, t: performance.now(), moved: 0, hist: [] };
        this.cam.vx = this.cam.vy = 0;
      } else if (this.ptrs.size === 2) {
        const v = [...this.ptrs.values()];
        this.pinch = { d: Math.hypot(v[0]!.x - v[1]!.x, v[0]!.y - v[1]!.y), mx: null, my: null };
        this.drag = null;
      }
      this.wake();
    });
    c.addEventListener('pointermove', (e) => {
      const p = this.ptrs.get(e.pointerId);
      const l = this.loc(e);
      if (!p) {
        if (e.pointerType === 'mouse') {
          const s = pick(this.stars, l.x, l.y);
          if (s !== this.hover) {
            this.hover = s;
            c.style.cursor = s ? 'pointer' : 'grab';
            this.wake();
          }
        }
        return;
      }
      p.x = l.x;
      p.y = l.y;
      if (this.ptrs.size === 2 && this.pinch) {
        const v = [...this.ptrs.values()];
        const d = Math.hypot(v[0]!.x - v[1]!.x, v[0]!.y - v[1]!.y);
        const mx = (v[0]!.x + v[1]!.x) / 2,
          my = (v[0]!.y + v[1]!.y) / 2;
        if (this.pinch.d > 0) {
          this.cam.pinchTo((this.cam.z * d) / this.pinch.d, mx, my);
          if (this.pinch.mx !== null && this.pinch.my !== null)
            this.cam.pan(mx - this.pinch.mx, my - this.pinch.my);
        }
        this.pinch = { d, mx, my };
        this.wake();
        return;
      }
      if (this.drag) {
        const dx = l.x - this.drag.x,
          dy = l.y - this.drag.y;
        this.drag.x = l.x;
        this.drag.y = l.y;
        this.drag.moved += Math.abs(dx) + Math.abs(dy);
        this.cam.pan(dx, dy);
        const now = performance.now();
        this.drag.hist.push({ t: now, dx, dy });
        while (this.drag.hist.length && now - this.drag.hist[0]!.t > 90) this.drag.hist.shift();
        if (this.drag.moved > 6) c.style.cursor = 'grabbing';
        this.wake();
      }
    });
    const end = (e: PointerEvent): void => {
      if (!this.ptrs.has(e.pointerId)) return;
      this.ptrs.delete(e.pointerId);
      if (this.pinch) {
        if (this.ptrs.size < 2) this.pinch = null;
        if (this.ptrs.size === 1) {
          const p = [...this.ptrs.values()][0]!;
          this.drag = { x: p.x, y: p.y, t: performance.now(), moved: 99, hist: [] };
        }
        return;
      }
      if (!this.drag) return;
      const now = performance.now();
      const l = this.loc(e);
      if (this.drag.moved < 7 && now - this.drag.t < 400) this.tap(l.x, l.y, now);
      else if (!reduced() && this.drag.hist.length > 1) {
        let sx = 0,
          sy = 0;
        for (const h of this.drag.hist) {
          sx += h.dx;
          sy += h.dy;
        }
        const st = Math.max(16, now - this.drag.hist[0]!.t);
        this.cam.vx = (sx / st) * 16;
        this.cam.vy = (sy / st) * 16;
      }
      this.drag = null;
      c.style.cursor = this.hover ? 'pointer' : 'grab';
      this.wake();
    };
    c.addEventListener('pointerup', end);
    c.addEventListener('pointercancel', end);
    c.addEventListener('pointerleave', () => {
      if (!this.drag && this.hover) {
        this.hover = null;
        this.wake();
      }
    });
    c.addEventListener(
      'wheel',
      (e) => {
        e.preventDefault();
        const l = this.loc(e);
        this.cam.zoomBy(Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0016)), l.x, l.y);
        this.wake();
      },
      { passive: false },
    );
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) this.wake();
    });
  }

  private tap(x: number, y: number, now: number): void {
    const s = pick(this.stars, x, y);
    if (s) {
      this.lastTap = 0;
      this.select(s.id);
      return;
    }
    if (now - this.lastTap < 320) {
      this.cam.zoomBy(2.2, x, y);
      this.lastTap = 0;
      this.wake();
      return;
    }
    this.lastTap = now;
    this.cb.onEmptyTap();
  }

  keydown(e: KeyboardEvent): boolean {
    const k = 60 / this.cam.z;
    if (e.key === '+' || e.key === '=') this.cam.zoomBy(1.6);
    else if (e.key === '-' || e.key === '_' || e.key === '−') this.cam.zoomBy(1 / 1.6);
    else if (e.key === '0') this.cam.flyTo(this.fitView());
    else if (e.key === 'ArrowLeft') this.cam.x -= k;
    else if (e.key === 'ArrowRight') this.cam.x += k;
    else if (e.key === 'ArrowUp') this.cam.y -= k;
    else if (e.key === 'ArrowDown') this.cam.y += k;
    else return false;
    this.wake();
    return true;
  }

  // ---------------------------------------------------------------- loop

  wake(): void {
    this.loop.wake();
  }

  destroy(): void {
    this.loop.stop();
  }

  private busy(now: number): boolean {
    const c = this.cam;
    return !!(
      c.flight ||
      c.zoomA ||
      this.drag ||
      this.pinch ||
      this.comet ||
      this.flares.length ||
      this.playing ||
      this.introOn ||
      Math.abs(c.vx) > 0.02 ||
      Math.abs(c.vy) > 0.02 ||
      Math.abs(this.focusMix - (this.sel ? 1 : 0)) > 0.003 ||
      Math.abs(this.searchMix - (this.search ? 1 : 0)) > 0.003 ||
      (this.sel && now - this.selT0 < 800) ||
      (this.search && !reduced() && now - this.search.t0 < PULSE_MS)
    );
  }

  private frame(now: number): boolean {
    if (!this.model) return false;
    if (this.playing) {
      const v = this.playV0 + ((now - this.playT0) / 14000) * 1000;
      this.setTime(Math.min(1000, v));
      this.onPlayTick?.(Math.min(1000, v));
      if (v >= 1000) this.playing = false;
    }
    if (this.cam.flight) this.cam.stepFlight(now);
    else if (this.cam.zoomA) this.cam.stepZoom();
    else if (!this.drag && !this.pinch) this.cam.stepInertia();
    const rm = reduced();
    this.focusMix = lerp(this.focusMix, this.sel ? 1 : 0, rm ? 1 : 0.12);
    this.searchMix = lerp(this.searchMix, this.search ? 1 : 0, rm ? 1 : 0.1);
    if (this.introOn && now - this.introT0 > 3200) this.introOn = false;
    this.draw(now);
    return this.busy(now);
  }

  // ---------------------------------------------------------------- drawing

  private draw(now: number): void {
    const m = this.model!;
    const ctx = this.ctx;
    const W = this.cam.W,
      H = this.cam.H,
      z = this.cam.z,
      cx = W / 2,
      cy = H / 2;
    const camx = this.cam.x,
      camy = this.cam.y;
    const t = now / 1000;
    const rm = reduced();
    ctx.globalCompositeOperation = 'source-over';
    ctx.globalAlpha = 1;
    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, W, H);
    const introA = this.introOn ? clamp((now - this.introT0) / 1400, 0, 1) : 1;
    ctx.globalCompositeOperation = 'lighter';

    // distant field (parallax)
    const pz = 0.7 + 0.3 * Math.log2(1 + z);
    for (const L of this.field.layers) {
      const ox = -camx * L.f * pz,
        oy = -camy * L.f * pz;
      for (const b of L.buckets) {
        ctx.fillStyle = b.style;
        for (const p of b.pts) {
          let x = (p.x + ox) % TILE;
          if (x < 0) x += TILE;
          if (x > W) continue;
          let y = (p.y + oy) % TILE;
          if (y < 0) y += TILE;
          if (y > H) continue;
          ctx.fillRect(x, y, L.size, L.size);
        }
      }
    }

    // Milky Way, fading as you zoom in
    const bandF = clamp(1.4 - z / 8, 0.3, 1) * (0.4 + 0.6 * introA);
    for (const b of this.field.bandBlobs) {
      const r = b.r * z,
        sx = (b.x - camx) * z + cx,
        sy = (b.y - camy) * z + cy;
      if (sx + r < 0 || sx - r > W || sy + r < 0 || sy - r > H) continue;
      ctx.globalAlpha = b.a * bandF;
      ctx.drawImage(this.sp.band, sx - r, sy - r, r * 2, r * 2);
    }
    ctx.globalCompositeOperation = 'source-over';
    for (const b of this.field.lanes) {
      const r = b.r * z,
        sx = (b.x - camx) * z + cx,
        sy = (b.y - camy) * z + cy;
      if (sx + r < 0 || sx - r > W || sy + r < 0 || sy - r > H) continue;
      ctx.globalAlpha = b.a * 0.6 * bandF;
      ctx.drawImage(this.sp.lane, sx - r, sy - r, r * 2, r * 2);
    }
    ctx.globalCompositeOperation = 'lighter';
    for (let k = 0; k < 2; k++) {
      ctx.globalAlpha = 1;
      ctx.fillStyle = k ? 'rgba(255,244,226,.36)' : 'rgba(236,230,220,.18)';
      for (const p of this.field.bandDust) {
        if (p.b !== k) continue;
        const sx = (p.x - camx) * z + cx,
          sy = (p.y - camy) * z + cy;
        if (sx < 0 || sx > W || sy < 0 || sy > H) continue;
        ctx.fillRect(sx, sy, p.s, p.s);
      }
    }
    // constellation glow: density, not decoration
    const counts = new Map<string, number>();
    for (const h of m.hubs)
      counts.set(
        h.id,
        h.stars.reduce((c, s) => c + (this.visible(s) ? 1 : 0), 0),
      );
    for (const h of m.hubs) {
      const n = counts.get(h.id) ?? 0;
      if (!n) continue;
      const r = h.s * 1.5 * z,
        sx = (h.x - camx) * z + cx,
        sy = (h.y - camy) * z + cy;
      if (sx + r < 0 || sx - r > W || sy + r < 0 || sy - r > H) continue;
      ctx.globalAlpha = (0.03 + 0.02 * Math.sqrt(n / 24)) * clamp(1.4 - z / 6, 0.25, 1) * introA;
      ctx.drawImage(this.sp.hub, sx - r, sy - r, r * 2, r * 2);
    }
    ctx.globalAlpha = 1;

    // star states
    const zr = Math.pow(z, 0.42),
      span = (m.now - m.tMin) * 0.012;
    const sel = this.sel,
      search = this.search;
    for (const s of m.stars) {
      s._on = false;
      if (!this.visible(s)) continue;
      const sx = (s.x - camx) * z + cx,
        sy = (s.y - camy) * z + cy;
      let r = clamp(s.base * zr, 0.9, 26);
      let a = 0.52 + s.imp * 0.55;
      if (this.timeT !== Infinity) {
        const ap = clamp((this.timeT - s.t) / span, 0, 1);
        a *= ap;
        r *= 1 + 1.3 * (1 - ap);
      }
      if (s.bornT) {
        const qb = (now - s.bornT) / 1100;
        if (qb < 1) {
          r *= 1 + 1.8 * (1 - easeOut(qb));
          a = Math.min(1.3, a + 0.6 * (1 - qb));
        } else s.bornT = 0;
      }
      if (this.introOn) a *= 0.3 + 0.7 * clamp((now - this.introT0 - s.dc * 0.9) / 1000, 0, 1);
      if (!rm) {
        a *= 0.88 + 0.12 * Math.sin(t * s.sp + s.ph);
        if (t > s.gl) {
          const gg = (t - s.gl) / 0.8;
          if (gg < 1) a *= 1 + 0.5 * Math.sin(Math.PI * gg);
          else s.gl = t + 25 + Math.random() * 80;
        }
      }
      if (s.earlier) {
        a *= 0.42;
        r *= 0.85;
      }
      if (sel && s !== sel && !this.selNear.has(s.id)) a *= lerp(1, 0.26, this.focusMix);
      if (search) {
        if (search.set.has(s.id)) {
          a = Math.min(1.3, a * (1 + 0.4 * this.searchMix));
          r *= 1 + 0.25 * this.searchMix;
        } else {
          const rp = clamp(
            (now - search.t0 - (search.dist.get(s.id) ?? 0) * 0.5) / RIPPLE_MS,
            0,
            1,
          );
          a *= lerp(1, 0.2, rp * this.searchMix);
        }
      }
      if (s === sel) r *= 1.35;
      if (s === this.hover) {
        r *= 1.15;
        a = Math.min(1.3, a * 1.25);
      }
      const g = r * 9;
      if (sx + g < 0 || sx - g > W || sy + g < 0 || sy - g > H) continue;
      s._sx = sx;
      s._sy = sy;
      s._r = r;
      s._a = a;
      s._on = a > 0.04;
    }

    // constellation lines (MST per hub)
    const eA =
      smooth(0.7, 1.5, z) *
      (1 - smooth(10, 18, z)) *
      0.16 *
      (sel ? lerp(1, 0.4, this.focusMix) : 1) *
      (search ? lerp(1, 0.3, this.searchMix) : 1) *
      introA;
    if (eA > 0.005) {
      ctx.globalCompositeOperation = 'source-over';
      ctx.lineWidth = 0.8;
      ctx.strokeStyle = `rgba(255,255,255,${eA})`;
      ctx.beginPath();
      for (const h of m.hubs) {
        for (const [A, B] of h.edges) {
          if (!this.visible(A) || !this.visible(B)) continue;
          const ax = (A.x - camx) * z + cx,
            ay = (A.y - camy) * z + cy;
          const bx = (B.x - camx) * z + cx,
            by = (B.y - camy) * z + cy;
          if ((ax < 0 && bx < 0) || (ax > W && bx > W) || (ay < 0 && by < 0) || (ay > H && by > H))
            continue;
          ctx.moveTo(ax, ay);
          ctx.lineTo(bx, by);
        }
      }
      ctx.stroke();
    }
    // history threads: a replaced fact and what replaced it
    const hA = smooth(1.2, 2.6, z) * 0.45;
    if (hA > 0.01) {
      ctx.lineWidth = 1;
      ctx.strokeStyle = `${THREAD}${hA})`;
      ctx.beginPath();
      for (const [A, B] of m.threads) {
        if (!this.visible(A) || !this.visible(B)) continue;
        ctx.moveTo((A.x - camx) * z + cx, (A.y - camy) * z + cy);
        ctx.lineTo((B.x - camx) * z + cx, (B.y - camy) * z + cy);
      }
      ctx.stroke();
    }
    // focus links to neighbours
    const cardLeft = this.layout.cardLeft();
    if (sel && this.focusMix > 0.02) {
      const p = easeOut(clamp((now - this.selT0) / 700, 0, 1));
      const sx = (sel.x - camx) * z + cx,
        sy = (sel.y - camy) * z + cy;
      ctx.lineWidth = 1;
      const histIds = new Set<string>();
      for (const [A, B] of m.threads) {
        if (A === sel) histIds.add(B.id);
        if (B === sel) histIds.add(A.id);
      }
      for (const id of this.selNear) {
        const o = m.byId.get(id);
        if (!o || !this.visible(o)) continue;
        const ox = (o.x - camx) * z + cx,
          oy = (o.y - camy) * z + cy;
        if (cardLeft !== null && ox > cardLeft) continue;
        ctx.strokeStyle = histIds.has(id)
          ? `${THREAD}${0.6 * this.focusMix})`
          : `rgba(255,255,255,${0.22 * this.focusMix})`;
        ctx.beginPath();
        ctx.moveTo(sx, sy);
        ctx.lineTo(lerp(sx, ox, p), lerp(sy, oy, p));
        ctx.stroke();
      }
    }

    // stars
    ctx.globalCompositeOperation = 'lighter';
    for (const s of m.stars) {
      if (!s._on) continue;
      const g = s._r * 9,
        aa = Math.min(1, s._a),
        spr = this.sp.glow[s.bin]!;
      ctx.globalAlpha = aa;
      ctx.drawImage(spr, s._sx - g / 2, s._sy - g / 2, g, g);
      if (s._a > 1) {
        ctx.globalAlpha = s._a - 1;
        ctx.drawImage(spr, s._sx - g / 2, s._sy - g / 2, g, g);
      }
      if ((s.imp > 0.84 || s === sel || (search && search.top === s)) && z > 0.5) {
        const k = s._r * (s === sel ? 20 : 14);
        ctx.globalAlpha = aa * (s === sel ? 0.42 : 0.2);
        ctx.drawImage(this.sp.spike, s._sx - k / 2, s._sy - k / 2, k, k);
      }
      if (z > 2.5) {
        ctx.globalAlpha = aa * smooth(2.5, 5, z);
        ctx.fillStyle = '#fff';
        ctx.beginPath();
        ctx.arc(s._sx, s._sy, Math.max(0.6, s._r * 0.3), 0, 6.283);
        ctx.fill();
      }
    }

    // selection ring, best-match pulse, hover ring
    ctx.globalCompositeOperation = 'source-over';
    if (sel && sel._on) {
      const grow = easeOut(clamp((now - this.selT0) / 520, 0, 1));
      const rr = (sel._r * 2.1 + 11) * (1.6 - 0.6 * grow);
      ctx.globalAlpha = 0.9 * this.focusMix * grow;
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 1.25;
      ctx.beginPath();
      ctx.arc(sel._sx, sel._sy, rr, 0, 6.283);
      ctx.stroke();
    }
    if (search?.top && search.top !== sel && search.top._on && !rm && now - search.t0 < PULSE_MS) {
      const q = ((now - search.t0) / 1800) % 1;
      ctx.globalAlpha = (1 - q) * 0.6 * this.searchMix;
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 1.1;
      ctx.beginPath();
      ctx.arc(search.top._sx, search.top._sy, search.top._r * 2 + 6 + q * 26, 0, 6.283);
      ctx.stroke();
    }
    const hov = this.hover;
    if (hov && hov !== sel && hov._on) {
      ctx.globalAlpha = 0.45;
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(hov._sx, hov._sy, hov._r * 2 + 7, 0, 6.283);
      ctx.stroke();
    }
    // flares on new stars
    for (let i = this.flares.length - 1; i >= 0; i--) {
      const f = this.flares[i]!,
        q = (now - f.t0) / FLARE_MS;
      if (q >= 1) {
        this.flares.splice(i, 1);
        continue;
      }
      const p = this.cam.w2s(f.s);
      ctx.globalCompositeOperation = 'lighter';
      ctx.globalAlpha = 1 - q;
      const G = 30 + 90 * (1 - q);
      ctx.drawImage(this.sp.glow[0]!, p.x - G / 2, p.y - G / 2, G, G);
      ctx.globalCompositeOperation = 'source-over';
      ctx.globalAlpha = (1 - q) * 0.7;
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.arc(p.x, p.y, 6 + 60 * easeOut(q), 0, 6.283);
      ctx.stroke();
    }
    // the comet from the composer
    const c = this.comet;
    if (c && now >= c.t0) {
      const s = c.s,
        p = clamp((now - c.t0) / c.dur, 0, 1),
        e = easeIO(p),
        tp = this.cam.w2s(s);
      const mx = lerp(c.fx, tp.x, e),
        my = lerp(c.fy, tp.y, e);
      const nx = -(tp.y - c.fy),
        ny = tp.x - c.fx,
        nl = Math.hypot(nx, ny) || 1;
      const arc = Math.sin(Math.PI * e) * 70;
      const px = mx + (nx / nl) * arc,
        py = my + (ny / nl) * arc;
      c.trail.push({ x: px, y: py });
      if (c.trail.length > 22) c.trail.shift();
      ctx.globalCompositeOperation = 'lighter';
      for (let i = 1; i < c.trail.length; i++) {
        const A = c.trail[i - 1]!,
          B = c.trail[i]!,
          k = i / c.trail.length;
        ctx.globalAlpha = k * 0.7;
        ctx.strokeStyle = 'rgb(200,216,255)';
        ctx.lineWidth = 1 + 2 * k;
        ctx.beginPath();
        ctx.moveTo(A.x, A.y);
        ctx.lineTo(B.x, B.y);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
      ctx.drawImage(this.sp.glow[0]!, px - 16, py - 16, 32, 32);
      ctx.globalCompositeOperation = 'source-over';
      if (p >= 1) {
        s.unborn = false;
        s.bornT = now;
        this.flares.push({ s, t0: now });
        this.comet = null;
        c.onLand?.();
        this.cb.onLanded?.(s.id);
      }
    }

    this.drawLabels(now, counts, cardLeft);
    ctx.shadowBlur = 0;
    ctx.globalAlpha = 1;
  }

  private drawLabels(now: number, counts: Map<string, number>, cardLeft: number | null): void {
    const ctx = this.ctx,
      m = this.model!;
    const W = this.cam.W,
      H = this.cam.H,
      z = this.cam.z,
      cx = W / 2,
      cy = H / 2;
    const narrow = this.layout.isNarrow();
    const placer = new Placer(this.layout.reserved());
    ctx.shadowColor = 'rgba(0,0,0,.95)';
    ctx.shadowBlur = 8;
    const sel = this.sel,
      search = this.search;
    const hubA =
      (1 - smooth(2.0, 3.8, z)) *
      (this.introOn ? clamp((now - this.introT0 - 300) / 900, 0, 1) : 1) *
      (sel ? lerp(1, 0.3, this.focusMix) : 1) *
      (search ? lerp(1, 0.45, this.searchMix) : 1);
    if (hubA > 0.01) {
      const fs = Math.round(lerp(narrow ? 16 : 18, narrow ? 14 : 15, smooth(0.4, 2.2, z)));
      ctx.textAlign = 'left';
      const order = [...m.hubs].sort((a, b) => (counts.get(b.id) ?? 0) - (counts.get(a.id) ?? 0));
      for (const h of order) {
        const n = counts.get(h.id) ?? 0;
        if (!n) continue;
        const x = (h.x - this.cam.x) * z + cx;
        const y = (h.y - this.cam.y) * z + cy - h.s * 0.95 * z - 12;
        if (x < 0 || x > W || y < 20 || y > H + 20) continue;
        ctx.font = `500 ${fs}px ${DISPLAY_FONT}`;
        const w1 = ctx.measureText(h.name).width;
        ctx.font = `400 13px ${UI_FONT}`;
        const cnt = String(n),
          w2 = ctx.measureText(cnt).width;
        const x0 = clamp(x - (w1 + 7 + w2) / 2, 12, W - (w1 + 7 + w2) - 12);
        if (!placer.fits({ x: x0 - 4, y: y - fs, w: w1 + 7 + w2 + 8, h: fs + 8 })) continue;
        ctx.font = `500 ${fs}px ${DISPLAY_FONT}`;
        ctx.globalAlpha = hubA * 0.92;
        ctx.fillStyle = '#f2f2f3';
        ctx.fillText(h.name, x0, y);
        ctx.font = `400 13px ${UI_FONT}`;
        ctx.globalAlpha = hubA * 0.7;
        ctx.fillStyle = '#b4b4b8';
        ctx.fillText(cnt, x0 + w1 + 7, y);
      }
    }
    const lz = smooth(2.2, 3.4, z);
    const cand: [number, Star][] = [];
    for (const s of m.stars) {
      if (!s._on) continue;
      let pr = -1;
      if (s === sel) pr = 100;
      else if (s === this.hover) pr = 90;
      else if (s.created && now - s.created < 7000) pr = 80;
      else if (search?.set.has(s.id)) pr = 60 + s.imp;
      else if (lz > 0.01) pr = s.imp * 10;
      if (pr >= 0) cand.push([pr, s]);
    }
    cand.sort((a, b) => b[0] - a[0]);
    let count = 0;
    const budget = narrow ? 28 : 70;
    const limitRight = cardLeft ?? W - 10;
    for (const [pr, s] of cand) {
      if (count > budget) break;
      const strong = pr >= 60,
        la = strong ? 1 : lz;
      if (la < 0.02) continue;
      const title = this.layout.titleOf(s.id);
      if (!title) continue;
      ctx.font = `500 13px ${UI_FONT}`;
      const text = title.length > 44 ? `${title.slice(0, 42)}…` : title;
      const w = ctx.measureText(text).width;
      const offset = (s === sel ? s._r * 2.1 + 11 : s._r * 1.6) + 9;
      const sub = z > 8 || strong;
      const at = placeStarLabel(
        { sx: s._sx, sy: s._sy, offset, width: w, height: sub ? 32 : 17, limitRight },
        placer,
      );
      if (!at) continue;
      ctx.globalAlpha = s === sel ? 1 : clamp(Math.min(1, s._a * 1.25) * la, 0, 0.95);
      ctx.fillStyle = s.earlier ? '#9a9a9e' : '#f2f2f3';
      ctx.fillText(text, at.x, at.y);
      if (sub) {
        ctx.font = `400 12px ${UI_FONT}`;
        ctx.globalAlpha *= 0.8;
        ctx.fillStyle = '#b4b4b8';
        ctx.fillText(this.layout.subOf(s), at.x, at.y + 16);
      }
      count++;
    }
  }
}

export const DAY_MS = DAY;
