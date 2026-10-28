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
