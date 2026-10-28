// Pre-rendered sprites: 24 age-coloured glows, a white glow, a four-point spike, soft blobs.

import { ageRGB, BINS, binDays, rgbStr, type RGB } from './palette';

function canvas(size: number): [HTMLCanvasElement, CanvasRenderingContext2D] {
  const cv = document.createElement('canvas');
  cv.width = cv.height = size;
  return [cv, cv.getContext('2d')!];
}

export function glowSprite(c: RGB): HTMLCanvasElement {
  const [cv, g] = canvas(128);
  const gr = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  gr.addColorStop(0, 'rgba(255,255,255,1)');
  gr.addColorStop(0.05, rgbStr(c, 1));
  gr.addColorStop(0.12, rgbStr(c, 0.6));
  gr.addColorStop(0.28, rgbStr(c, 0.16));
  gr.addColorStop(0.55, rgbStr(c, 0.045));
  gr.addColorStop(1, rgbStr(c, 0));
  g.fillStyle = gr;
  g.fillRect(0, 0, 128, 128);
  return cv;
}

export function spikeSprite(): HTMLCanvasElement {
  const [cv, g] = canvas(128);
  const lg = g.createLinearGradient(0, 0, 128, 0);
  lg.addColorStop(0, 'rgba(255,255,255,0)');
  lg.addColorStop(0.5, 'rgba(255,255,255,.85)');
  lg.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = lg;
  g.fillRect(0, 63.5, 128, 1);
  const vg = g.createLinearGradient(0, 0, 0, 128);
  vg.addColorStop(0, 'rgba(255,255,255,0)');
  vg.addColorStop(0.5, 'rgba(255,255,255,.85)');
  vg.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = vg;
  g.fillRect(63.5, 0, 1, 128);
  return cv;
}

export function softSprite(c: RGB, a0: number): HTMLCanvasElement {
  const [cv, g] = canvas(256);
  const gr = g.createRadialGradient(128, 128, 0, 128, 128, 128);
  gr.addColorStop(0, rgbStr(c, a0));
  gr.addColorStop(0.45, rgbStr(c, a0 * 0.35));
  gr.addColorStop(1, rgbStr(c, 0));
  g.fillStyle = gr;
  g.fillRect(0, 0, 256, 256);
  return cv;
}

export interface Sprites {
  glow: HTMLCanvasElement[];
  white: HTMLCanvasElement;
  spike: HTMLCanvasElement;
  band: HTMLCanvasElement;
  lane: HTMLCanvasElement;
  hub: HTMLCanvasElement;
}

let cache: Sprites | null = null;

export function sprites(): Sprites {
  if (!cache) {
    cache = {
      glow: Array.from({ length: BINS }, (_, b) => glowSprite(ageRGB(binDays(b)))),
      white: glowSprite([255, 255, 255]),
      spike: spikeSprite(),
      band: softSprite([214, 204, 186], 0.5),
      lane: softSprite([0, 0, 0], 0.9),
      hub: softSprite([235, 232, 226], 0.5),
    };
  }
  return cache;
}
