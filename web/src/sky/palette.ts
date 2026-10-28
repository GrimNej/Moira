// A star's colour is its age (App. H): stops follow the blackbody sequence of real star colours,
// tuned for contrast on black, interpolated on log(1 + days).

export type RGB = [number, number, number];

const AGE_STOPS: [number, RGB][] = [
  [0, [176, 200, 255]],
  [10, [206, 220, 255]],
  [45, [236, 240, 255]],
  [150, [255, 246, 234]],
  [420, [255, 228, 194]],
  [900, [255, 204, 150]],
];
export const BINS = 24;
const AGE_MAX = Math.log1p(900);
export const DAY = 86_400_000;

export const clamp = (v: number, a: number, b: number): number => (v < a ? a : v > b ? b : v);
export const lerp = (a: number, b: number, t: number): number => a + (b - a) * t;
export const smooth = (a: number, b: number, v: number): number => {
  const t = clamp((v - a) / (b - a), 0, 1);
  return t * t * (3 - 2 * t);
};
export const easeIO = (t: number): number => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);
export const easeOut = (t: number): number => 1 - (1 - t) ** 3;

export function ageRGB(days: number): RGB {
  const x = Math.log1p(clamp(days, 0, 900));
  for (let i = 1; i < AGE_STOPS.length; i++) {
    const [da, ca] = AGE_STOPS[i - 1]!;
    const [db, cb] = AGE_STOPS[i]!;
    const xa = Math.log1p(da);
    const xb = Math.log1p(db);
    if (x <= xb) {
      const t = (x - xa) / (xb - xa);
      return [0, 1, 2].map((k) => Math.round(lerp(ca[k]!, cb[k]!, t))) as RGB;
    }
  }
  return AGE_STOPS[AGE_STOPS.length - 1]![1];
}

export const rgbStr = (c: RGB, a = 1): string => `rgba(${c[0]},${c[1]},${c[2]},${a})`;
export const binOf = (days: number): number =>
  clamp(Math.round((Math.log1p(clamp(days, 0, 900)) / AGE_MAX) * (BINS - 1)), 0, BINS - 1);
export const binDays = (b: number): number => Math.expm1((b / (BINS - 1)) * AGE_MAX);
export const ageCss = (t: number, now: number): string => rgbStr(ageRGB((now - t) / DAY));

export const THREAD = 'rgba(255,224,170,';
export const UI_FONT =
  'system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif';
export const DISPLAY_FONT = '"Jost Variable",Jost,Futura,"Century Gothic",system-ui,sans-serif';
