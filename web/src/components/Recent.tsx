// Recent (§4.3.9): grouped by local day with sticky headers, filters, 50 per page. Also the
// accessible alternative to the canvas (the skip link lands here).

import { useEffect, useRef, useState } from 'preact/hooks';

import { api } from '../api/client';
import type { RecentItem } from '../api/types';
import { sourceShort } from '../lib/format';
import { dayLabel, time12 } from '../lib/time';
import { engine } from '../sky/engine';
import { ageCss } from '../sky/palette';
import { tz } from '../state/session';
import { sky } from '../state/sky';

const FILTERS: [string, string][] = [
  ['all', 'All'],
  ['links', 'Links'],
  ['todos', 'To-dos'],
  ['people', 'People'],
  ['facts', 'Facts'],
  ['ideas', 'Ideas'],
  ['notes', 'Notes'],
];

export function Recent({ onOpen }: { onOpen?: () => void }) {
  const [filter, setFilter] = useState('all');
  const [items, setItems] = useState<RecentItem[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const list = useRef<HTMLDivElement>(null);
  const now = engine()?.model?.now ?? Date.now();

  async function load(reset: boolean): Promise<void> {
    setLoading(true);
    try {
      const res = await api.recent({ cursor: reset ? null : next, kind: filter });
      setItems(reset ? res.items : [...items, ...res.items]);
      setNext(res.next_cursor);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load(true);
  }, [filter, sky.value?.cursor]);

  let last = '';
  return (
    <div class="recent">
      <div class="filters" role="toolbar" aria-label="Show only">
        {FILTERS.map(([key, label]) => (
          <button
            type="button"
            key={key}
            class="press"
            aria-pressed={filter === key}
            onClick={() => setFilter(key)}
          >
            {label}
          </button>
        ))}
      </div>
      <div
        ref={list}
        id="rlist"
        class="rlist"
        tabIndex={-1}
        onScroll={(e) => {
          const el = e.currentTarget as HTMLDivElement;
          if (next && !loading && el.scrollTop + el.clientHeight > el.scrollHeight - 200)
            void load(false);
        }}
      >
        {items.length === 0 && !loading && <p class="empty-note">Nothing here yet.</p>}
        {items.map((s) => {
          const d = dayLabel(s.t, tz.value, now);
          const head = d !== last ? <div class="rday">{d}</div> : null;
          last = d;
          return (
            <div key={s.id}>
              {head}
              <button
                type="button"
                class="rrow press"
                onClick={() => {
                  onOpen?.();
                  engine()?.select(s.id);
                }}
              >
                <span class="dot" style={{ '--c': ageCss(s.t, now) }} />
                <span class="t">{s.title}</span>
                <span class="m num">{time12(s.t, tz.value)}</span>
                <span class="s">
                  {s.hub.name}, {sourceShort(s.source)}
                </span>
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
