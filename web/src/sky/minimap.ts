// The 72 px mini sky in an answer (§4.3.7): frames the answer's constellation, rings the star.

import { sprites } from './sprites';
import type { Model, Star } from './stars';

export function drawMini(cv: HTMLCanvasElement, model: Model, best: Star): void {
  const S = 2;
  const g = cv.getContext('2d');
  if (!g) return;
  const W = cv.width,
    H = cv.height;
  const sp = sprites();
  g.fillStyle = '#000';
  g.fillRect(0, 0, W, H);
  const hub = model.hubById.get(best.hub);
  const span = (hub ? hub.s : 120) * 2.6;
  const k = W / span,
    ox = W / 2 - best.x * k,
    oy = H / 2 - best.y * k;
  g.globalCompositeOperation = 'lighter';
  for (const s of model.stars) {
    const x = s.x * k + ox,
      y = s.y * k + oy;
    if (x < -10 || x > W + 10 || y < -10 || y > H + 10) continue;
    const sz = (6 + s.imp * 10) * S;
    g.globalAlpha = 0.25 + s.imp * 0.45;
    g.drawImage(sp.glow[s.bin]!, x - sz / 2, y - sz / 2, sz, sz);
  }
  const hx = best.x * k + ox,
    hy = best.y * k + oy;
  g.globalAlpha = 1;
  g.drawImage(sp.glow[best.bin]!, hx - 26, hy - 26, 52, 52);
  g.globalCompositeOperation = 'source-over';
  g.strokeStyle = 'rgba(255,255,255,.95)';
  g.lineWidth = 1.5 * S;
  g.beginPath();
  g.arc(hx, hy, 11 * S, 0, 6.283);
  g.stroke();
}
