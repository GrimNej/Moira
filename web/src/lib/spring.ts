// A critically damped spring (App. N.5): k = (2π/response)², c = 4π/response. The velocity of a
// drag carries over; any new touch cancels it. Reduced motion jumps to the target.

export interface SpringState {
  y: number;
  anim: { dead: boolean } | null;
}

export const reducedMotion = (): boolean =>
  typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;

export function springTo(
  st: SpringState,
  target: number,
  v0: number,
  response: number,
  onStep: (y: number) => void,
  onDone?: () => void,
): void {
  if (st.anim) st.anim.dead = true;
  const a = { dead: false };
  st.anim = a;
  if (reducedMotion()) {
    st.y = target;
    onStep(st.y);
    onDone?.();
    return;
  }
  const k = ((2 * Math.PI) / response) ** 2;
  const c = (4 * Math.PI) / response;
  let v = v0 || 0;
  let last = performance.now();
  const tick = (now: number): void => {
    if (a.dead) return;
    const dt = Math.min(0.032, (now - last) / 1000);
    last = now;
    v += (-k * (st.y - target) - c * v) * dt;
    st.y += v * dt;
    onStep(st.y);
    if (Math.abs(st.y - target) < 0.5 && Math.abs(v) < 20) {
      st.y = target;
      onStep(st.y);
      st.anim = null;
      onDone?.();
      return;
    }
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

/** Rubber band above the top: overshoot·d·0.55 / (d + 0.55·overshoot). */
export function rubber(overshoot: number, d: number): number {
  return (overshoot * d * 0.55) / (d + 0.55 * overshoot);
}

/** Momentum projection with deceleration 0.998 (velocity in px/s). */
export function project(position: number, velocity: number): number {
  const d = 0.998;
  return position + ((velocity / 1000) * d) / (1 - d);
}
