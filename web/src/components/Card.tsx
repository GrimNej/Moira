// The card (§4.3.6): one memory, sections in order, each only if present. On desktop it grows
// out of its star; on phones it is a sheet. Move, Edit and Forget are quiet text buttons.

import { useEffect, useRef, useState } from 'preact/hooks';

import { api } from '../api/client';
import type { Card as CardData } from '../api/types';
import { focusTitle, rememberFocus, restoreFocus } from '../lib/a11y';
import { KIND_LABEL } from '../lib/format';
import { setBack } from '../lib/telegram';
import { short } from '../lib/time';
import { reducedMotion } from '../lib/spring';
import { bridge, engine } from '../sky/engine';
import { ageCss, clamp } from '../sky/palette';
import { tz } from '../state/session';
import { cardOpen, refreshSky, selected, why } from '../state/sky';
import { narrow, showToast } from '../state/ui';
import { useSheet } from './Sheet';

function Row({
  id,
  title,
  meta,
  t,
  now,
}: {
  id: string;
  title: string;
  meta: string;
  t: number;
  now: number;
}) {
  return (
    <button type="button" class="row press" onClick={() => engine()?.select(id)}>
      <span class="dot" style={{ '--c': ageCss(t, now) }} />
      <span class="t">{title}</span>
      <span class="m num">{meta}</span>
    </button>
  );
}

export function Card() {
  const el = useRef<HTMLElement>(null);
  const grab = useRef<HTMLDivElement>(null);
  const [card, setCard] = useState<CardData | null>(null);
  const [panel, setPanel] = useState<'none' | 'edit' | 'move'>('none');
  const [text, setText] = useState('');
  const [hubs, setHubs] = useState<{ id: string; name: string }[]>([]);
  const [filter, setFilter] = useState('');
  const id = selected.value;
  const now = engine()?.model?.now ?? Date.now();
  const sheet = useSheet(el, grab, {
    peek: () => innerHeight * 0.58,
    onState: (d) => {
      if (d === 'closed') engine()?.deselect();
    },
    onClosed: () => {
      if (el.current) el.current.hidden = true;
    },
  });

  useEffect(() => {
    if (!id) {
      close();
      return;
    }
    let live = true;
    setPanel('none');
    api
      .card(id)
      .then((c) => {
        if (!live) return;
        setCard(c);
        void api.opened(id).catch(() => undefined);
        if (narrow.value) openNow();
      })
      .catch(() => {
        if (live) showToast('That memory is gone.');
      });
    return () => {
      live = false;
    };
  }, [id]);

  function openNow(): void {
    const c = el.current;
    if (!c) return;
    rememberFocus();
    c.hidden = false;
    cardOpen.value = true;
    document.body.classList.add('card-open');
    setBack(() => engine()?.deselect());
    if (narrow.value) sheet.open(sheet.state() === 'full' ? 'full' : 'peek');
    requestAnimationFrame(() => focusTitle(c.querySelector('.card-scroll') as HTMLElement));
  }

  /** Desktop: the card grows out of the star (transform-origin at the star). */
  function bloom(starId: string): void {
    const c = el.current;
    if (!c || narrow.value) return;
    openNow();
    const r = c.getBoundingClientRect();
    const p = engine()?.screenOf(starId);
    if (p) {
      c.style.transformOrigin = `${clamp(p.x - r.left, -60, r.width + 60)}px ${clamp(p.y - r.top, 0, r.height)}px`;
    }
    if (reducedMotion())
      c.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 200, easing: 'ease' });
    else
      c.animate(
        [
          { transform: 'scale(.86)', opacity: 0 },
          { transform: 'scale(1)', opacity: 1 },
        ],
        {
          duration: 460,
          easing: 'cubic-bezier(.16,1,.3,1)',
        },
      );
  }

  function close(): void {
    const c = el.current;
    cardOpen.value = false;
    document.body.classList.remove('card-open');
    setBack(null);
    if (!c || c.hidden) {
      restoreFocus();
      return;
    }
    if (narrow.value) {
      sheet.close();
      restoreFocus();
      return;
    }
    const a = c.animate(
      reducedMotion()
        ? [{ opacity: 1 }, { opacity: 0 }]
        : [
            { transform: 'scale(1)', opacity: 1 },
            { transform: 'scale(.9)', opacity: 0 },
          ],
      { duration: reducedMotion() ? 150 : 220, easing: 'cubic-bezier(.4,0,1,1)' },
    );
    a.onfinish = () => {
      if (!cardOpen.value) c.hidden = true;
    };
    restoreFocus();
  }

  useEffect(() => {
    bridge.bloom = bloom;
  });

  async function forget(): Promise<void> {
    if (!card) return;
    const res = await api.forget(card.id);
    engine()?.deselect();
    await refreshSky();
    showToast('Forgotten', {
      label: 'Undo',
      run: () => {
        void api.undo(res.undo_group_id).then(async () => {
          await refreshSky();
          engine()?.select(card.id);
        });
      },
    });
  }

  async function saveEdit(): Promise<void> {
    if (!card || !text.trim()) return;
    await api.edit(card.id, text.trim());
    setPanel('none');
    setCard(await api.card(card.id));
    showToast('Saved. Filing it again.');
  }

  async function moveTo(target: { hub_id?: string; new_hub_name?: string }): Promise<void> {
    if (!card) return;
    const res = await api.move(card.id, target);
    setPanel('none');
    setCard(await api.card(card.id));
    await refreshSky();
    showToast('Moved', {
      label: 'Undo',
      run: () => {
        void api.undo(res.group_id).then(async () => {
          setCard(await api.card(card.id));
          await refreshSky();
        });
      },
    });
  }

  const c = card;
  return (
    <aside ref={el} class="card" hidden aria-labelledby="cTitle">
      <div ref={grab} class="grab-zone">
        <div class="grab" aria-hidden="true" />
      </div>
      <button
        type="button"
        class="close press"
        aria-label="Close"
        onClick={() => engine()?.deselect()}
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
        >
          <path d="M6 6l12 12M18 6L6 18" />
        </svg>
      </button>
      {c && (
        <div class="card-scroll" key={c.id}>
          <h2 id="cTitle" class="reveal">
            {c.title}
          </h2>
          <p class="sub reveal">
            {KIND_LABEL[c.kind]} in {c.hub.name}
            {c.isEarlier ? ', earlier version' : ''}
          </p>
          {why.value && <p class="why reveal">{why.value}</p>}
          {c.now && (
            <section class="reveal">
              <h3>Now</h3>
              <p class="now-line">{c.now}</p>
            </section>
          )}
          {c.replacedBy && (
            <section class="reveal">
              <h3>Replaced by</h3>
              <button
                type="button"
                class="hist press"
                onClick={() => engine()?.select(c.replacedBy!.id)}
              >
                <span>{c.replacedBy.title}</span>
                <span class="m num">{short(c.replacedBy.t, tz.value, now)}</span>
              </button>
            </section>
          )}
          {c.earlier.length > 0 && (
            <section class="reveal">
              <h3>Earlier</h3>
              {c.earlier.map((e) => (
                <button
                  type="button"
                  class="hist press"
                  key={e.id}
                  onClick={() => engine()?.select(e.id)}
                >
                  <s>{e.title}</s>
                  <span class="m num">until {short(e.until, tz.value, now)}</span>
                </button>
              ))}
            </section>
          )}
          <section class="reveal">
            <h3>You sent, from {c.sent.sourceLabel}</h3>
            <div class="bubble-wrap">
              <p class="bubble">
                {c.sent.text || '(no words)'}
                <span class="time num">{c.sent.localTime}</span>
              </p>
            </div>
          </section>
          {c.list.length > 0 && (
            <section class="reveal">
              <h3>Read as a list</h3>
              {c.list.map((item) => (
                <div class="row" key={item}>
                  <span class="dot" style={{ '--c': ageCss(c.saved.t, now) }} />
                  <span class="t">{item}</span>
                </div>
              ))}
            </section>
          )}
          {c.found && (
            <section class="reveal">
              <h3>It found, from {c.found.method}</h3>
              <div class="found">
                <p>{c.found.text}</p>
                {(c.found.verified !== null || c.found.sources.length > 0) && (
                  <div class="foot">
                    {c.found.verified !== null && (
                      <span class="pill">{c.found.verified ? 'Verified' : 'Possible match'}</span>
                    )}
                    {c.found.sources[0] && <span>{hostOf(c.found.sources[0].url)}</span>}
                  </div>
                )}
              </div>
            </section>
          )}
          {c.guess && (
            <section class="reveal">
              <h3>Its guess</h3>
              <p class="guess">{c.guess}</p>
            </section>
          )}
          <dl class="kv reveal">
            <dt>Saved</dt>
            <dd class="num">
              {c.saved.local}
              <span class="rel">{c.saved.relative}</span>
            </dd>
            {c.before && (
              <>
                <dt>Before this</dt>
                <dd>
                  <button
                    type="button"
                    class="linkbtn"
                    onClick={() => engine()?.select(c.before!.id)}
                  >
                    {c.before.title}
                  </button>
                  <span class="rel">{c.before.gap}</span>
                </dd>
              </>
            )}
          </dl>
          {c.nearby.length > 0 && (
            <section class="reveal">
              <h3>Nearby in {c.hub.name}</h3>
              {c.nearby.map((o) => (
                <Row
                  key={o.id}
                  id={o.id}
                  title={o.title}
                  t={o.t}
                  now={now}
                  meta={short(o.t, tz.value, now)}
                />
              ))}
            </section>
          )}
          {panel === 'edit' && (
            <section>
              <h3>Edit what you sent</h3>
              <textarea
                class="edit-box"
                value={text}
                onInput={(e) => setText((e.target as HTMLTextAreaElement).value)}
              />
              <div class="actions">
                <button type="button" class="primary-btn press" onClick={() => void saveEdit()}>
                  Save
                </button>
                <button type="button" class="press" onClick={() => setPanel('none')}>
                  Cancel
                </button>
              </div>
            </section>
          )}
          {panel === 'move' && (
            <section>
              <h3>Move to a constellation</h3>
              <div class="picker">
                <input
                  placeholder="Find or name a constellation"
                  aria-label="Find or name a constellation"
                  value={filter}
                  onInput={(e) => setFilter((e.target as HTMLInputElement).value)}
                />
                {hubs
                  .filter(
                    (h) => h.name.toLowerCase().includes(filter.toLowerCase()) && h.id !== c.hub.id,
                  )
                  .slice(0, 8)
                  .map((h) => (
                    <button
                      type="button"
                      class="row press"
                      key={h.id}
                      onClick={() => void moveTo({ hub_id: h.id })}
                    >
                      <span class="t">{h.name}</span>
                    </button>
                  ))}
                {filter.trim() && (
                  <button
                    type="button"
                    class="row press"
                    onClick={() => void moveTo({ new_hub_name: filter.trim() })}
                  >
                    <span class="t">New constellation “{filter.trim()}”</span>
                  </button>
                )}
              </div>
            </section>
          )}
          <div class="actions reveal">
            <button
              type="button"
              class="press"
              onClick={() => {
                setFilter('');
                setPanel('move');
                void api.hubs().then((r) => setHubs(r.hubs));
              }}
            >
              Move
            </button>
            <button
              type="button"
              class="press"
              onClick={() => {
                setText(c.sent.text);
                setPanel('edit');
              }}
            >
              Edit
            </button>
            <button type="button" class="press" onClick={() => void forget()}>
              Forget
            </button>
          </div>
        </div>
      )}
    </aside>
  );
}

function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return '';
  }
}
