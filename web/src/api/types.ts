// Shared types (App. N.4), mirrored by the backend's API responses. All times are UTC ms.

export type Kind = 'link' | 'idea' | 'fact' | 'person' | 'todo' | 'note';
export type Source =
  | 'typed'
  | 'voice'
  | 'screenshot'
  | 'instagram'
  | 'youtube'
  | 'github'
  | 'web'
  | 'x'
  | 'tiktok'
  | 'facebook'
  | 'threads'
  | 'video'
  | 'forward'
  | 'location'
  | 'contact'
  | 'other';
export type HubKind = 'shelf' | 'topic' | 'person' | 'fact';

export interface SkyHub {
  id: string;
  name: string;
  kind: HubKind;
  x: number;
  y: number;
  count: number;
  now: string;
}

export interface SkyPayload {
  v: 1;
  cursor: string;
  stars: {
    id: string[];
    x: number[];
    y: number[];
    kind: Kind[];
    hub: string[];
    t: number[];
    imp: number[];
    flags: number[];
    title: string[];
    source: Source[];
  };
  hubs: SkyHub[];
  threads: [string, string][];
  removed: string[];
  template_now?: number;
}

export const FLAG = { earlier: 1, corrected: 2, research: 4, pinned: 8, sample: 16 } as const;

export interface Card {
  id: string;
  title: string;
  kind: Kind;
  hub: { id: string; name: string };
  isEarlier: boolean;
  now: string | null;
  replacedBy: { id: string; title: string; t: number } | null;
  earlier: { id: string; title: string; until: number }[];
  sent: { text: string; source: Source; sourceLabel: string; t: number; localTime: string };
  list: string[];
  found: {
    method: string;
    text: string;
    verified: boolean | null;
    sources: { url: string; title: string }[];
  } | null;
  guess: string;
  saved: { t: number; local: string; relative: string };
  before: { id: string; title: string; gap: string } | null;
  nearby: { id: string; title: string; t: number }[];
  sourceName?: string;
}

export interface Clues {
  source: string | null;
  time_label: string | null;
  terms: string[];
  intent: 'lookup' | 'list' | 'count';
}

export interface AnswerData {
  answer: string;
  citations: { id: string; why: string }[];
  also: string[];
  confidence: 'high' | 'medium' | 'low' | 'not_found';
  tier: 'instant' | 'answer' | 'deep';
  turn_id: number;
  conversation_id?: string;
  count?: number | null;
  items?: string[];
}

export type AskEvent =
  | { event: 'clues'; data: Clues }
  | { event: 'lit'; data: { ids: string[]; top: string | null } }
  | { event: 'status'; data: { text: string } }
  | { event: 'answer'; data: AnswerData }
  | { event: 'error'; data: { message: string; fallback_ids: string[] } }
  | { event: 'done'; data: Record<string, never> };

export interface RecentItem {
  id: string;
  title: string;
  kind: Kind;
  source: Source;
  hub: { id: string; name: string };
  t: number;
}

export interface Me {
  id: string;
  kind: 'owner' | 'tester' | 'judge' | 'sandbox';
  display_name: string;
  tz: string;
  caps: { spent_today: number; cap_today: number };
  version: string;
}

export interface LiveEvent {
  event: 'filed' | 'updated' | 'removed' | 'hub' | 'ping';
  data: Record<string, unknown>;
}
