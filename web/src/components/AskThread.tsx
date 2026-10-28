// The conversation (§4.3.7): the user's bubble, understood clues as tokens, a specific status
// line, then the answer. Answers are announced politely to screen readers.

import { useEffect, useRef } from 'preact/hooks';

import { turns } from '../state/chat';
import { engine } from '../sky/engine';
import { short } from '../lib/time';
import { tz } from '../state/session';
import { narrow } from '../state/ui';
import { AnswerBlock } from './AnswerBlock';
import type { Clues } from '../api/types';

function clueTokens(c: Clues): string[] {
  const out: string[] = [];
  if (c.source) out.push(c.source.charAt(0).toUpperCase() + c.source.slice(1));
  if (c.time_label) out.push(c.time_label);
  for (const t of c.terms.slice(0, 4)) out.push(t.length <= 3 ? t.toUpperCase() : t);
  return out;
}

export function AskThread() {
  const end = useRef<HTMLDivElement>(null);
  const list = turns.value;
  useEffect(() => {
    end.current?.scrollIntoView({ block: narrow.value ? 'nearest' : 'end' });
  }, [list]);
  const model = engine()?.model;
  const now = model?.now ?? Date.now();
  return (
    <>
      {list.map((t) =>
        t.savedNote ? (
          <div class="msg me" key={t.id}>
            <span class="saved-as">Saved</span>
            <p>{t.question}</p>
          </div>
        ) : (
          <div key={t.id} class="turn">
            <div class="msg me">
              <p>{t.question}</p>
            </div>
            <div class="msg ai">
              {t.clues && clueTokens(t.clues).length > 0 && (
                <div class="understood">
                  {clueTokens(t.clues).map((c, i) => (
                    <span class="clue" key={c} style={{ animationDelay: `${i * 90}ms` }}>
                      {c}
                    </span>
                  ))}
                </div>
              )}
              {t.status && !t.answer && (
                <p class="status">
                  <i />
                  {t.status}
                </p>
              )}
              {!t.status && !t.answer && !t.error && (
                <p class="status">
                  <i />
                  Looking through your memories
                </p>
              )}
              {t.error && !t.answer && <p>{t.error}</p>}
              {t.error && t.fallback.length > 0 && !t.answer && (
                <div class="also">
                  {t.fallback.slice(0, 3).map((id) => {
                    const s = model?.byId.get(id);
                    return s ? (
                      <button
                        type="button"
                        key={id}
                        class="row press"
                        onClick={() => engine()?.select(id)}
                      >
                        <span class="t">{s.title}</span>
                        <span class="m num">{short(s.t, tz.value, now)}</span>
                      </button>
                    ) : null;
                  })}
                </div>
              )}
              {t.answer && <AnswerBlock turn={t} a={t.answer} />}
            </div>
          </div>
        ),
      )}
      <div ref={end} />
    </>
  );
}
