// One answer (§4.3.7): plain text, the result block with its mini sky and Show in sky, Also close,
// and Found it / Not it.

import { useEffect, useRef } from 'preact/hooks';

import { api } from '../api/client';
import type { AnswerData } from '../api/types';
import { short } from '../lib/time';
import { engine } from '../sky/engine';
import { drawMini } from '../sky/minimap';
import { ageCss } from '../sky/palette';
import { setFeedback, type Turn } from '../state/chat';
import { tz } from '../state/session';
import { why } from '../state/sky';
import { narrow, panelState } from '../state/ui';

function whyLine(turn: Turn): string {
  const c = turn.clues;
  if (!c) return '';
  const parts: string[] = [];
  if (c.source) parts.push(`from ${c.source.charAt(0).toUpperCase()}${c.source.slice(1)}`);
  if (c.time_label) parts.push(`saved ${c.time_label}`);
  if (c.terms.length) parts.push(`about ${c.terms.slice(0, 3).join(' and ')}`);
  return parts.length ? `Matched: ${parts.join(', ')}.` : '';
}

function open(id: string, reason: string): void {
  why.value = reason;
  if (narrow.value) panelState.value = 'closed';
  engine()?.select(id);
}

export function AnswerBlock({ turn, a }: { turn: Turn; a: AnswerData }) {
  const mini = useRef<HTMLCanvasElement>(null);
  const best = a.citations[0]?.id ?? null;
  const model = engine()?.model ?? null;
  const star = best ? (model?.byId.get(best) ?? null) : null;
  const now = model?.now ?? Date.now();
  const also = a.also.filter((id) => id !== best).slice(0, 3);
  const reason = whyLine(turn);

  useEffect(() => {
    if (mini.current && model && star) drawMini(mini.current, model, star);
  }, [model, star]);

  const hub = star ? model?.hubById.get(star.hub) : undefined;
  return (
    <>
      <p>{a.answer}</p>
      {star && (
        <button
          type="button"
          class="result press"
          aria-label={`Show ${star.title} in the sky`}
          onClick={() => open(star.id, reason)}
        >
          <canvas ref={mini} width={144} height={144} aria-hidden="true" />
          <span class="r-title">{star.title}</span>
          <span class="r-sub">
            <span class="r-meta num">
              {hub?.name ?? ''}, {short(star.t, tz.value, now)}
            </span>
          </span>
          <span class="r-go">Show in sky</span>
        </button>
      )}
      {a.items && a.items.length > 1 && (
        <div class="also">
          <h4>{a.count ?? a.items.length} in all</h4>
          {a.items.slice(0, 20).map((id) => {
            const s = model?.byId.get(id);
            return s ? (
              <button type="button" key={id} class="row press" onClick={() => open(id, reason)}>
                <span class="dot" style={{ '--c': ageCss(s.t, now) }} />
                <span class="t">{s.title}</span>
                <span class="m num">{short(s.t, tz.value, now)}</span>
              </button>
            ) : null;
          })}
        </div>
      )}
      {also.length > 0 && (
        <div class="also">
          <h4>{a.confidence === 'not_found' ? 'Closest' : 'Also close'}</h4>
          {also.map((id) => {
            const s = model?.byId.get(id);
            return s ? (
              <button type="button" key={id} class="row press" onClick={() => open(id, reason)}>
                <span class="dot" style={{ '--c': ageCss(s.t, now) }} />
                <span class="t">{s.title}</span>
                <span class="m num">{short(s.t, tz.value, now)}</span>
              </button>
            ) : null;
          })}
        </div>
      )}
      {a.turn_id > 0 && (
        <div class="fb" role="group" aria-label="Was this right?">
          {(['found', 'not_it'] as const).map((v) => (
            <button
              type="button"
              key={v}
              class="press"
              aria-pressed={turn.feedback === v}
              onClick={() => {
                setFeedback(turn.id, v);
                void api.feedback(a.turn_id, v).catch(() => undefined);
              }}
            >
              {v === 'found' ? 'Found it' : 'Not it'}
            </button>
          ))}
          {turn.feedback && (
            <span>
              {turn.feedback === 'found'
                ? 'Thanks. That helps the next search.'
                : 'Thanks. Try adding when or where you saw it.'}
            </span>
          )}
        </div>
      )}
    </>
  );
}
