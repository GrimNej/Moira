// What the composer and the live stream do: ask, save (comet → star → toast with Undo), and
// apply live updates from GET /api/events.

import { api, headers } from './api/client';
import { readSse } from './api/sse';
import { engine } from './sky/engine';
import { addSavedNote, ask } from './state/chat';
import { saveMedia, saveText } from './state/capture';
import { lit, refreshSky, timeValue } from './state/sky';
import { asked, narrow, panelState, showToast, tab } from './state/ui';

/** Saves waiting for their `filed` event, with where the comet starts. */
const pendingSaves = new Map<string, { from: { x: number; y: number } }>();
// A fast filer can announce the star before the save request has returned; keep it briefly.
const earlyFiled = new Map<string, Record<string, unknown>>();

function track(id: string, from: { x: number; y: number }): void {
  pendingSaves.set(id, { from });
  const early = earlyFiled.get(id);
  if (early) {
    earlyFiled.delete(id);
    void onFiled(early);
  }
}

function composerPoint(): { x: number; y: number } {
  const el = document.querySelector('.composer');
  const r = el?.getBoundingClientRect();
  return r
    ? { x: r.left + r.width * 0.8, y: r.top + r.height / 2 }
    : { x: innerWidth / 2, y: innerHeight };
}

export async function askQuestion(text: string): Promise<void> {
  const e = engine();
  timeValue.value = 1000;
  e?.setTime(1000);
  asked.value = true;
  tab.value = 'ask';
  if (narrow.value) {
    e?.deselect();
    panelState.value = 'peek';
  }
  await ask(text, {
    onLit: (ids, top) => {
      lit.value = { ids, top };
      if (ids.length) engine()?.light(ids, top);
    },
    onAnswer: (a) => {
      const best = a.citations[0]?.id;
      if (best) engine()?.glideTo(best);
      if (narrow.value) panelState.value = 'peek';
    },
    onError: (fallback) => {
      if (fallback.length) {
        lit.value = { ids: fallback, top: fallback[0] ?? null };
        engine()?.light(fallback, fallback[0] ?? null);
      }
    },
  });
}

export async function saveNugget(text: string): Promise<void> {
  timeValue.value = 1000;
  engine()?.setTime(1000);
  engine()?.deselect();
  lit.value = null;
  engine()?.clearLight();
  if (narrow.value) panelState.value = 'closed';
  else {
    tab.value = 'ask';
    addSavedNote(text);
  }
  const from = composerPoint();
  const res = await saveText(text);
  if (!res) {
    showToast('Saved offline. It will send when you are back online.');
    return;
  }
  track(res.id, from);
}

export async function saveFiles(files: File[]): Promise<void> {
  const from = composerPoint();
  const res = await saveMedia(files);
  if (res) track(res.id, from);
  else showToast('That file could not be saved. Send a screenshot or a voice note.');
}

export async function saveVoice(blob: Blob): Promise<void> {
  const from = composerPoint();
  const res = await saveMedia([blob], '', true);
  if (res) track(res.id, from);
  else showToast('That voice note could not be saved. Try again.');
}

async function onFiled(data: Record<string, unknown>): Promise<void> {
  const id = String(data.id ?? '');
  await refreshSky();
  const e = engine();
  const pending = pendingSaves.get(id);
  if (!pending) {
    earlyFiled.set(id, data);
    setTimeout(() => earlyFiled.delete(id), 30_000);
    return;
  }
  if (!e) return;
  pendingSaves.delete(id);
  const hubName = String(data.hub_name ?? 'your sky');
  const nowLines = (data.now as string[] | undefined) ?? [];
  const land = (): void => {
    const undo = {
      label: 'Undo',
      run: () => {
        void api.forget(id).then(() => refreshSky());
      },
    };
    if (data.fact_changed && nowLines[0]) showToast(nowLines[0].replace(/\.$/, ''), undo);
    else showToast(`Filed in ${hubName}`, undo);
  };
  // The engine takes the new payload on the next render; wait a few frames for the star.
  for (let i = 0; i < 30 && !e.has(id); i++) {
    await new Promise((r) => requestAnimationFrame(() => r(null)));
  }
  if (e.has(id)) e.cometTo(id, pending.from, land);
  else land();
}

let stream: AbortController | null = null;

/** Live updates (filed, updated, removed, hub). Reconnects with a short backoff. */
export function startLive(): void {
  if (stream) return;
  stream = new AbortController();
  const signal = stream.signal;
  let delay = 1000;
  const connect = async (): Promise<void> => {
    while (!signal.aborted) {
      try {
        const res = await fetch('/api/events', {
          credentials: 'same-origin',
          headers: headers('GET'),
          signal,
        });
        if (!res.ok) throw new Error(String(res.status));
        delay = 1000;
        await readSse(res, (f) => {
          if (f.event === 'filed') void onFiled(f.data as Record<string, unknown>);
          else if (f.event === 'updated' || f.event === 'removed' || f.event === 'hub')
            void refreshSky();
        });
      } catch {
        if (signal.aborted) return;
      }
      await new Promise((r) => setTimeout(r, delay));
      delay = Math.min(30_000, delay * 2);
    }
  };
  void connect();
}

export function stopLive(): void {
  stream?.abort();
  stream = null;
}
