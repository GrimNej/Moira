// Saving from the web (§4.3.8): text now, voice and screenshots as media; offline queue.

import { signal } from '@preact/signals';

import { api, headers } from '../api/client';
import { pending, enqueue, flush } from '../lib/offline-queue';

export const waiting = signal(0);

export async function saveText(text: string): Promise<{ id: string } | null> {
  if (!navigator.onLine) {
    await enqueue({ kind: 'text', text });
    waiting.value = await pending();
    return null;
  }
  try {
    return await api.save(text);
  } catch {
    await enqueue({ kind: 'text', text });
    waiting.value = await pending();
    return null;
  }
}

export async function saveMedia(
  files: File[] | Blob[],
  text = '',
  audio = false,
): Promise<{ id: string } | null> {
  const form = new FormData();
  if (audio) form.append('audio', files[0] as Blob, 'voice.webm');
  else (files as File[]).forEach((f) => form.append('images', f, f.name || 'screenshot.jpg'));
  if (text) form.append('text', text);
  const res = await fetch('/api/nuggets/media', {
    method: 'POST',
    credentials: 'same-origin',
    headers: headers('POST'),
    body: form,
  });
  if (!res.ok) return null;
  return (await res.json()) as { id: string };
}

export async function retryQueue(): Promise<void> {
  await flush(async (item) => {
    if (item.kind === 'text') await api.save(item.text);
  });
  waiting.value = await pending();
}

addEventListener('online', () => {
  void retryQueue();
});
