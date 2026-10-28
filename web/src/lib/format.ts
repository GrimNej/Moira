// Small text helpers for the UI (copy rules, §4.3.14).

import type { Kind, Source } from '../api/types';

export const KIND_LABEL: Record<Kind, string> = {
  link: 'Link',
  idea: 'Idea',
  fact: 'Fact',
  person: 'Person',
  todo: 'To-do',
  note: 'Note',
};

export const SOURCE_SHORT: Partial<Record<Source, string>> = {
  instagram: 'Instagram',
  youtube: 'YouTube',
  github: 'GitHub',
  web: 'Web',
  typed: 'Typed',
  voice: 'Voice',
  screenshot: 'Screenshot',
  x: 'X',
  tiktok: 'TikTok',
  facebook: 'Facebook',
  threads: 'Threads',
  video: 'Video',
  forward: 'Forward',
  location: 'Location',
  contact: 'Contact',
  other: 'File',
};

export function sourceShort(s: string): string {
  return SOURCE_SHORT[s as Source] ?? s;
}

export function truncate(s: string, n: number): string {
  return s.length > n ? `${s.slice(0, n - 1)}…` : s;
}

export function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

export type Piece = { text: string; href?: string };

/** Split text into plain pieces and http(s) links (§10.1: no other scheme ever becomes a link). */
export function linkPieces(text: string): Piece[] {
  const out: Piece[] = [];
  const re = /\bhttps?:\/\/[^\s<>"']+/gi;
  let last = 0;
  for (const m of text.matchAll(re)) {
    const raw = m[0].replace(/[.,;:!?)\]]+$/, '');
    const at = m.index ?? 0;
    let href: string | undefined;
    try {
      const u = new URL(raw);
      if (u.protocol === 'http:' || u.protocol === 'https:') href = u.href;
    } catch {
      href = undefined;
    }
    if (!href) continue;
    if (at > last) out.push({ text: text.slice(last, at) });
    out.push({ text: raw, href });
    last = at + raw.length;
  }
  if (last < text.length) out.push({ text: text.slice(last) });
  return out;
}
