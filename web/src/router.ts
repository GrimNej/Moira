// Routes (§4.3.2): /, /?star=<id>, /recent, /n/<id>, /settings, /login. History API, no library.

import { signal } from '@preact/signals';

export type Route =
  | { name: 'home'; star: string | null; from: string | null; saved: string | null }
  | { name: 'recent' }
  | { name: 'settings' }
  | { name: 'login'; token: string | null };

export function parseRoute(path: string, search: string, hash: string): Route {
  const q = new URLSearchParams(search);
  if (path === '/login') {
    const h = new URLSearchParams(hash.replace(/^#/, ''));
    return { name: 'login', token: h.get('t') };
  }
  if (path === '/recent') return { name: 'recent' };
  if (path === '/settings') return { name: 'settings' };
  const n = path.match(/^\/n\/([\w-]+)$/);
  return {
    name: 'home',
    star: n ? (n[1] ?? null) : q.get('star'),
    from: q.get('from'),
    saved: q.get('saved'),
  };
}

export const route = signal<Route>(parseRoute(location.pathname, location.search, location.hash));

export function navigate(url: string, replace = false): void {
  if (replace) history.replaceState(null, '', url);
  else history.pushState(null, '', url);
  route.value = parseRoute(location.pathname, location.search, location.hash);
}

addEventListener('popstate', () => {
  route.value = parseRoute(location.pathname, location.search, location.hash);
});
