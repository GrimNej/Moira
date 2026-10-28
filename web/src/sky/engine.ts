// The one sky engine of the page, and the layout it reads from the DOM (§4.3.3).

import { panelState, narrow } from '../state/ui';
import { tz } from '../state/session';
import { short } from '../lib/time';
import { sourceShort } from '../lib/format';
import type { Rect } from './labels';
import type { Layout, Region, SkyEngine } from './renderer';
import type { Star } from './stars';

let current: SkyEngine | null = null;

/** Set by the card: grow it out of the star at 62 % of the flight (§4.3.5). */
export const bridge: { bloom: (id: string) => void } = { bloom: () => undefined };

export function setEngine(e: SkyEngine | null): void {
  current = e;
}

export function engine(): SkyEngine | null {
  return current;
}

function local(
  el: Element | null,
  origin: DOMRect,
): { l: number; t: number; r: number; b: number; h: number } | null {
  if (!el) return null;
  const r = el.getBoundingClientRect();
  if (!r.width && !r.height) return null;
  return {
    l: r.left - origin.left,
    t: r.top - origin.top,
    r: r.right - origin.left,
    b: r.bottom - origin.top,
    h: r.height,
  };
}

export function domLayout(canvas: HTMLCanvasElement): Layout {
  const q = (sel: string): Element | null => document.querySelector(sel);
  return {
    isNarrow: () => narrow.value,
    reserved(): Rect[] {
      const o = canvas.getBoundingClientRect();
      const out: Rect[] = [];
      for (const sel of ['.timeline', '.zoom', '.lit']) {
        const b = local(q(sel), o);
        if (!b) continue;
        const r = { x: b.l, y: b.t, w: b.r - b.l, h: b.h };
        if (r.h > 60) {
          r.y += 20;
          r.h -= 20;
        }
        out.push(r);
      }
      return out;
    },
    cardLeft(): number | null {
      if (narrow.value) return null;
      const card = q('.card');
      if (!card || (card as HTMLElement).hidden) return null;
      const b = local(card, canvas.getBoundingClientRect());
      return b ? b.l - 8 : null;
    },
    region(withCard: boolean): Region {
      const o = canvas.getBoundingClientRect();
      const W = o.width,
        H = o.height;
      let l = 0,
        r = W,
        t = 0,
        b = H;
      const tl = local(q('.timeline'), o);
      if (tl) b = tl.t + 22;
      const card = q('.card') as HTMLElement | null;
      const open = !!card && !card.hidden;
      if (!narrow.value) {
        t = 56;
        if (withCard || open) {
          const k = card && !card.hidden ? local(card, o) : null;
          r = k ? k.l - 12 : W - Math.min(392, W - 24) - 24;
        }
      } else {
        t = 84;
        if (panelState.value !== 'closed') b = Math.min(b, H - Math.max(innerHeight * 0.58, 430));
        if (withCard || open) b = Math.min(b, H - innerHeight * 0.58);
      }
      if (r - l < 160) {
        l = 0;
        r = W;
      }
      if (b - t < 140) b = t + 140;
      return { l, r, t, b, w: r - l, h: b - t, cx: (l + r) / 2, cy: (t + b) / 2 };
    },
    titleOf(id: string): string | undefined {
      return current?.model?.byId.get(id)?.title || undefined;
    },
    subOf(s: Star): string {
      const now = current?.model?.now ?? Date.now();
      return `${short(s.t, tz.value, now)}, ${sourceShort(s.source)}`;
    },
  };
}
