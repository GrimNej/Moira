// The timeline (§4.3.10): one bar per week, coloured by age, so it is also the colour key. An
// ARIA slider; dragging shows the sky as of that date; play replays its growth in 14 s.

import { useEffect, useRef, useState } from 'preact/hooks';

import { longDay, short } from '../lib/time';
import { engine } from '../sky/engine';
import { ageRGB, clamp, DAY, rgbStr, UI_FONT } from '../sky/palette';
import { tz } from '../state/session';
import { sky, timeValue } from '../state/sky';

export function Timeline() {
  const wrap = useRef<HTMLDivElement>(null);
  const cv = useRef<HTMLCanvasElement>(null);
  const [playing, setPlaying] = useState(false);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const v = timeValue.value;
  const e = engine();
  const model = e?.model ?? null;
  const now = model?.now ?? Date.now();
  const tMin = model?.tMin ?? now - 30 * DAY;
  const t = v >= 999.5 ? Infinity : tMin + ((now - tMin) * v) / 1000;
  const count = model ? model.stars.filter((s) => t === Infinity || s.t <= t).length : 0;

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      const r = el.getBoundingClientRect();
      setSize({ w: r.width, h: r.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const c = cv.current;
    if (!c || !size.w || !model) return;
    const dpr = Math.min(2, devicePixelRatio || 1);
    c.width = Math.round(size.w * dpr);
    c.height = Math.round(size.h * dpr);
    const g = c.getContext('2d')!;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, size.w, size.h);
    const TW = size.w,
      TH = size.h;
    const weeks = Math.max(1, Math.ceil((now - tMin) / (7 * DAY)));
    const counts = new Array<number>(weeks).fill(0);
    for (const s of model.stars)
      counts[Math.min(weeks - 1, Math.floor((s.t - tMin) / (7 * DAY)))]!++;
    const max = Math.max(3, ...counts);
    const bw = TW / weeks,
      base = TH - 16,
      top = 4;
    for (let i = 0; i < weeks; i++) {
      const mid = tMin + (i + 0.5) * 7 * DAY;
      const n = counts[i]!;
      const h = n ? Math.max(2, (base - top) * Math.sqrt(n / max)) : 1;
      g.fillStyle = rgbStr(ageRGB((now - mid) / DAY), n ? (mid <= t ? 0.95 : 0.22) : 0.12);
      g.fillRect(i * bw + 0.5, base - h, Math.max(1, bw - 1.5), h);
    }
    g.font = `12px ${UI_FONT}`;
    g.fillStyle = '#949498';
    const y0 = new Date(tMin).getUTCFullYear(),
      y1 = new Date(now).getUTCFullYear();
    for (let y = y0 + 1; y <= y1; y++) {
      const x = ((Date.UTC(y, 0, 1) - tMin) / (now - tMin)) * TW;
      if (x > 8 && x < TW - 40) {
        g.fillRect(x, base + 2, 1, 4);
        g.fillText(String(y), x + 4, TH - 2);
      }
    }
    const px = (v / 1000) * TW;
    g.fillStyle = '#fff';
    g.fillRect(Math.min(TW - 2, Math.max(0, px - 1)), top - 2, 2, base - top + 4);
  }, [size, v, model, now, tMin, t, sky.value]);

  useEffect(() => {
    const en = engine();
    if (!en) return;
    en.onPlayTick = (val) => {
      timeValue.value = val;
      if (val >= 1000) setPlaying(false);
    };
    return () => {
      en.onPlayTick = null;
    };
  }, [e]);

  const set = (val: number): void => {
    const next = clamp(val, 0, 1000);
    timeValue.value = next;
    engine()?.setTime(next);
  };
  const fromEvent = (ev: PointerEvent): number => {
    const r = wrap.current!.getBoundingClientRect();
    return ((ev.clientX - r.left) / r.width) * 1000;
  };
  const dragging = useRef(false);
  const label = t === Infinity ? 'Today' : short(t, tz.value, now);
  const valueText = t === Infinity ? 'Today' : `${longDay(t, tz.value)}, ${count} stars`;

  return (
    <div class="timeline">
      <button
        type="button"
        class="play press"
        aria-label={playing ? 'Pause the replay' : 'Replay how your sky grew'}
        onClick={() => {
          const en = engine();
          if (!en) return;
          if (playing) {
            en.stop();
            setPlaying(false);
            return;
          }
          setPlaying(true);
          en.play(v);
        }}
      >
        <svg viewBox="0 0 24 24">
          {playing ? (
            <path d="M8 5h3v14H8zM13 5h3v14h-3z" fill="currentColor" />
          ) : (
            <path d="M8 5.5v13l11-6.5z" fill="currentColor" />
          )}
        </svg>
      </button>
      <div
        ref={wrap}
        class="tl-wrap"
        role="slider"
        tabIndex={0}
        aria-label="Show the sky as it was on a date"
        aria-valuemin={0}
        aria-valuemax={1000}
        aria-valuenow={Math.round(v)}
        aria-valuetext={valueText}
        onPointerDown={(ev) => {
          dragging.current = true;
          (ev.currentTarget as HTMLElement).setPointerCapture(ev.pointerId);
          engine()?.stop();
          setPlaying(false);
          set(fromEvent(ev));
        }}
        onPointerMove={(ev) => {
          if (dragging.current) set(fromEvent(ev));
        }}
        onPointerUp={() => {
          dragging.current = false;
        }}
        onPointerCancel={() => {
          dragging.current = false;
        }}
        onKeyDown={(ev) => {
          if (ev.key === 'ArrowLeft') set(v - 10);
          else if (ev.key === 'ArrowRight') set(v + 10);
          else if (ev.key === 'Home') set(0);
          else if (ev.key === 'End') set(1000);
          else return;
          ev.preventDefault();
        }}
      >
        <canvas ref={cv} aria-hidden="true" />
        <div
          class="tl-label num"
          style={{ left: `${clamp((v / 1000) * size.w, 34, Math.max(34, size.w - 34))}px` }}
        >
          {label}
          {t !== Infinity && <span> {count} stars</span>}
        </div>
      </div>
    </div>
  );
}
