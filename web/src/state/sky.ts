// The sky's data and what the interface shares with the canvas engine.

import { signal } from '@preact/signals';

import { api } from '../api/client';
import type { SkyPayload } from '../api/types';

export const sky = signal<SkyPayload | null>(null);
export const selected = signal<string | null>(null);
export const why = signal<string>('');
export const lit = signal<{ ids: string[]; top: string | null } | null>(null);
/** Timeline position 0–1000; 1000 = today. */
export const timeValue = signal(1000);
export const cardOpen = signal(false);

export async function loadSky(): Promise<SkyPayload> {
  const p = await api.sky();
  sky.value = p;
  return p;
}

/** Merge a `?since=` delta into the payload (new or changed stars, removals). */
export function mergeDelta(base: SkyPayload, delta: SkyPayload): SkyPayload {
  const gone = new Set([...delta.removed, ...delta.stars.id]);
  const keep = base.stars.id.map((id, i) => (gone.has(id) ? -1 : i)).filter((i) => i >= 0);
  const cols = ['id', 'x', 'y', 'kind', 'hub', 't', 'imp', 'flags', 'title', 'source'] as const;
  const stars = Object.fromEntries(
    cols.map((c) => [c, [...keep.map((i) => base.stars[c][i]), ...delta.stars[c]]]),
  ) as SkyPayload['stars'];
  return { ...delta, stars, hubs: delta.hubs, threads: delta.threads, removed: [] };
}

export async function refreshSky(): Promise<void> {
  const cur = sky.value;
  if (!cur) {
    await loadSky();
    return;
  }
  const delta = await api.sky(cur.cursor);
  sky.value = mergeDelta(cur, delta);
}
