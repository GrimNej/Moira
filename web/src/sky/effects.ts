// Effects: the flare of a new star, the comet from the composer, the search ripple and pulse.

import type { Star } from './stars';

export interface Flare {
  s: Star;
  t0: number;
}

export interface Comet {
  s: Star;
  t0: number;
  dur: number;
  fx: number;
  fy: number;
  trail: { x: number; y: number }[];
  onLand?: () => void;
}

export interface Search {
  set: Set<string>;
  top: Star | null;
  t0: number;
  dist: Map<string, number>;
}

export const FLARE_MS = 1200;
export const COMET_MS = 1150;
export const PULSE_MS = 6000;
export const RIPPLE_MS = 450;
