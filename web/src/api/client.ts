// The API client. Cookie sessions on the web; a bearer token inside the Telegram Mini App
// (its cross-site iframe blocks cookies). Every write sends `X-Moira: 1` (CSRF guard, §10.1).

import { readSse, type SseFrame } from './sse';
import type { AskEvent, Card, Me, RecentItem, SkyPayload } from './types';

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

let bearer: string | null = null;
try {
  bearer = sessionStorage.getItem('moira.bearer');
} catch {
  bearer = null;
}

export function setBearer(token: string | null): void {
  bearer = token;
  try {
    if (token) sessionStorage.setItem('moira.bearer', token);
    else sessionStorage.removeItem('moira.bearer');
  } catch {
    // Storage can be blocked (private windows); the token then lives in memory only.
  }
}

export function headers(
  method: string,
  extra: Record<string, string> = {},
): Record<string, string> {
  const h: Record<string, string> = { ...extra };
  if (method !== 'GET' && method !== 'HEAD') h['X-Moira'] = '1';
  if (bearer) h['Authorization'] = `Bearer ${bearer}`;
  return h;
}

export async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, credentials: 'same-origin', headers: headers(method) };
  if (body !== undefined) {
    init.body = JSON.stringify(body);
    (init.headers as Record<string, string>)['Content-Type'] = 'application/json';
  }
  const res = await fetch(path, init);
  if (res.status === 204) return undefined as T;
  const data = (await res.json().catch(() => ({}))) as {
    error?: { code: string; message: string };
  };
  if (!res.ok) {
    throw new ApiError(
      res.status,
      data.error?.code ?? 'error',
      data.error?.message ?? res.statusText,
    );
  }
  return data as T;
}

export const api = {
  me: () => request<Me>('GET', '/api/me'),
  setTz: (tz: string) => request<Me>('PATCH', '/api/me', { tz }),
  sky: (since?: string) =>
    request<SkyPayload>('GET', since ? `/api/sky?since=${encodeURIComponent(since)}` : '/api/sky'),
  card: (id: string) => request<Card>('GET', `/api/nuggets/${encodeURIComponent(id)}`),
  opened: (id: string) => request<unknown>('POST', `/api/nuggets/${encodeURIComponent(id)}/opened`),
  recent: (q: { cursor?: string | null; kind?: string; source?: string; hub?: string }) => {
    const p = new URLSearchParams();
    if (q.cursor) p.set('cursor', q.cursor);
    if (q.kind && q.kind !== 'all') p.set('kind', q.kind);
    if (q.source) p.set('source', q.source);
    if (q.hub) p.set('hub', q.hub);
    const qs = p.toString();
    return request<{ items: RecentItem[]; next_cursor: string | null }>(
      'GET',
      `/api/recent${qs ? `?${qs}` : ''}`,
    );
  },
  save: (text: string) => request<{ id: string; status: string }>('POST', '/api/nuggets', { text }),
  edit: (id: string, user_text: string) =>
    request<{ version: number }>('PATCH', `/api/nuggets/${id}`, { user_text }),
  forget: (id: string) =>
    request<{ undo_group_id: string; undo_until: number }>('POST', `/api/nuggets/${id}/forget`),
  move: (id: string, target: { hub_id?: string; new_hub_name?: string }) =>
    request<{ group_id: string }>('POST', `/api/nuggets/${id}/move`, target),
  restore: (id: string) => request<{ group_id: string }>('POST', `/api/nuggets/${id}/restore`),
  undo: (group_id?: string) =>
    request<{ undone_group_id: string }>('POST', '/api/undo', group_id ? { group_id } : {}),
  hubs: () =>
    request<{ hubs: { id: string; name: string; kind: string; count: number }[] }>(
      'GET',
      '/api/hubs',
    ),
  feedback: (turnId: number, value: 'found' | 'not_it') =>
    request<unknown>('POST', `/api/turns/${turnId}/feedback`, { value }),
  saveInstead: (turnId: number) =>
    request<{ nugget_id: string }>('POST', `/api/turns/${turnId}/save-instead`),
  loginLink: (token: string) => request<unknown>('POST', '/api/auth/link', { token }),
  telegram: (init_data: string) =>
    request<{ bearer: string; user: Me }>('POST', '/api/auth/telegram', { init_data }),
  logout: () => request<unknown>('POST', '/api/auth/logout'),
  logoutOthers: () => request<unknown>('POST', '/api/auth/logout-others'),
  sandbox: () => request<{ user: Me }>('POST', '/api/sandbox'),
};

/** POST /api/ask and stream its events (§8.5). */
export async function ask(
  question: string,
  conversationId: string | null,
  onEvent: (e: AskEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch('/api/ask', {
    method: 'POST',
    credentials: 'same-origin',
    headers: headers('POST', { 'Content-Type': 'application/json' }),
    body: JSON.stringify({ question, conversation_id: conversationId }),
    signal,
  });
  if (!res.ok) {
    const data = (await res.json().catch(() => ({}))) as { error?: { message: string } };
    onEvent({
      event: 'error',
      data: {
        message: data.error?.message ?? 'Something went wrong. Try again.',
        fallback_ids: [],
      },
    });
    onEvent({ event: 'done', data: {} });
    return;
  }
  await readSse(res, (f: SseFrame) => onEvent(f as AskEvent));
}
