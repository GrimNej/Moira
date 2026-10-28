// Phone sheets (§4.3.3, §4.3.5): drag the grabber 1:1, rubber-band above the top, project
// momentum to pick the detent, settle with a critically damped spring. Any touch interrupts.

import { useEffect, useMemo } from 'preact/hooks';
import type { RefObject } from 'preact';

import { project, rubber, springTo, type SpringState } from '../lib/spring';
import { narrow } from '../state/ui';

export type Detent = 'closed' | 'peek' | 'full';

export interface SheetApi {
  state(): Detent;
  open(d?: Exclude<Detent, 'closed'>, v0?: number): void;
  close(v0?: number): void;
  reset(): void;
  visible(): number;
}

export function useSheet(
  el: RefObject<HTMLElement>,
  grab: RefObject<HTMLElement>,
  opts: { peek: () => number; onState?: (d: Detent) => void; onClosed?: () => void },
): SheetApi {
  const st = useMemo<SpringState & { state: Detent }>(
    () => ({ y: 0, anim: null, state: 'closed' }),
    [],
  );

  const api = useMemo<SheetApi>(() => {
    const full = (): number => el.current?.getBoundingClientRect().height || innerHeight * 0.88;
    const peekH = (): number => Math.min(full(), opts.peek());
    const targetY = (s: Detent): number =>
      s === 'full' ? 0 : s === 'peek' ? full() - peekH() : full() + 30;
    const apply = (y: number): void => {
      if (el.current) el.current.style.transform = `translateY(${y}px)`;
    };
    return {
      state: () => st.state,
      visible: () => (st.state === 'closed' ? 0 : full() - targetY(st.state)),
      open(d = 'peek', v0 = 0) {
        if (!narrow.value || !el.current) return;
        const wasClosed = st.state === 'closed';
        st.state = d;
        el.current.classList.add('shown');
        el.current.style.setProperty('--hide', `${targetY(d)}px`);
        if (wasClosed && !st.anim) {
          st.y = full() + 30;
          apply(st.y);
        }
        springTo(st, targetY(d), v0, 0.42, apply);
        opts.onState?.(d);
      },
      close(v0 = 0) {
        if (st.state === 'closed') return;
        st.state = 'closed';
        springTo(st, targetY('closed'), v0, 0.36, apply, () => {
          if (st.state === 'closed') {
            el.current?.classList.remove('shown');
            opts.onClosed?.();
          }
        });
        opts.onState?.('closed');
      },
      reset() {
        if (st.anim) st.anim.dead = true;
        st.anim = null;
        st.state = 'closed';
        if (el.current) {
          el.current.style.transform = '';
          el.current.classList.remove('shown');
        }
      },
    };
  }, []);

  useEffect(() => {
    const g = grab.current;
    if (!g) return;
    const full = (): number => el.current?.getBoundingClientRect().height || innerHeight * 0.88;
    let drag: { y0: number; s0: number; hist: { t: number; y: number }[] } | null = null;
    const down = (e: PointerEvent): void => {
      if (!narrow.value || st.state === 'closed') return;
      if ((e.target as HTMLElement).closest('button')) return;
      g.setPointerCapture(e.pointerId);
      if (st.anim) st.anim.dead = true;
      st.anim = null;
      drag = { y0: e.clientY, s0: st.y, hist: [{ t: performance.now(), y: e.clientY }] };
    };
    const move = (e: PointerEvent): void => {
      if (!drag) return;
      let y = drag.s0 + (e.clientY - drag.y0);
      if (y < 0) y = -rubber(-y, full());
      st.y = y;
      if (el.current) el.current.style.transform = `translateY(${y}px)`;
      drag.hist.push({ t: performance.now(), y: e.clientY });
      if (drag.hist.length > 6) drag.hist.shift();
    };
    const end = (): void => {
      if (!drag) return;
      const h = drag.hist;
      const a = h[0]!,
        b = h[h.length - 1]!;
      const v = ((b.y - a.y) / Math.max(16, b.t - a.t)) * 1000;
      drag = null;
      const projected = project(st.y, v);
      const peekY = full() - Math.min(full(), opts.peek());
      const cands: [Detent, number][] = [
        ['full', Math.abs(0 - projected)],
        ['peek', Math.abs(peekY - projected)],
        ['closed', Math.abs(full() + 30 - projected)],
      ];
      cands.sort((x, y) => x[1] - y[1]);
      const d = cands[0]![0];
      if (d === 'closed') api.close(v);
      else api.open(d, v);
    };
    g.addEventListener('pointerdown', down);
    g.addEventListener('pointermove', move);
    g.addEventListener('pointerup', end);
    g.addEventListener('pointercancel', end);
    return () => {
      g.removeEventListener('pointerdown', down);
      g.removeEventListener('pointermove', move);
      g.removeEventListener('pointerup', end);
      g.removeEventListener('pointercancel', end);
    };
  }, []);

  return api;
}
