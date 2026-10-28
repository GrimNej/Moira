// The column (§4.3.3): wordmark and scope, Ask | Recent, the content, the composer. On phones the
// conversation and Recent live in one bottom sheet.

import { useEffect, useRef } from 'preact/hooks';

import { askQuestion } from '../actions';
import { setBack } from '../lib/telegram';
import { engine } from '../sky/engine';
import { MONTHS, dayFull } from '../lib/time';
import { me, tz } from '../state/session';
import { sky, timeValue } from '../state/sky';
import { turns } from '../state/chat';
import { asked, mode, narrow, panelState, settingsOpen, tab } from '../state/ui';
import { AskThread } from './AskThread';
import { Composer } from './Composer';
import { Lately } from './Lately';
import { Recent } from './Recent';
import { Settings } from './Settings';
import { useSheet } from './Sheet';

const SUGGESTIONS = [
  'insta link about AI, ~2 weeks ago',
  'what’s my favorite fruit?',
  'that FPS fix',
  'Josh’s email',
  'palette from GitHub',
  'who are my best friends?',
];

function Scope() {
  const p = sky.value;
  const user = me.value;
  const e = engine();
  const sample = user?.kind === 'sandbox' || user?.kind === 'judge';
  if (!p) return <span class="scope num">{sample ? 'Sample memory' : 'Your sky'}</span>;
  const v = timeValue.value;
  const n = v < 999.5 && e ? e.countVisible() : p.stars.id.length;
  if (v < 999.5 && e) {
    return (
      <span class="scope num">
        Sky as of {dayFull(e.tOf(v), tz.value)}, {n} stars
      </span>
    );
  }
  const first = Math.min(...p.stars.t, Date.now());
  const d = new Date(first);
  const since = p.stars.t.length ? ` since ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}` : '';
  const who = sample ? 'Sample memory, times in Kathmandu time' : 'Your sky';
  return (
    <span class="scope num">
      {who}, {n} stars{since}
    </span>
  );
}

function Arrow() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="1.8"
      stroke-linecap="round"
      stroke-linejoin="round"
    >
      <path d="M5 12h13M13 6l6 6-6 6" />
    </svg>
  );
}

export function Column() {
  const panel = useRef<HTMLElement>(null);
  const grab = useRef<HTMLDivElement>(null);
  const sample = me.value?.kind === 'sandbox' || me.value?.kind === 'judge';
  const sheet = useSheet(panel, grab, {
    peek: () => Math.max(innerHeight * 0.58, 430),
    onState: (d) => {
      if (panelState.value !== d) panelState.value = d;
      setBack(d === 'closed' ? null : () => sheet.close());
    },
  });

  useEffect(() => {
    const d = panelState.value;
    if (!narrow.value) {
      sheet.reset();
      return;
    }
    if (d === 'closed') sheet.close();
    else sheet.open(d);
  }, [panelState.value, narrow.value]);

  const ask = (q: string): void => {
    mode.value = 'ask';
    void askQuestion(q);
  };
  const showSugg = sample && !asked.value && turns.value.length === 0;
  useEffect(() => {
    document.body.classList.toggle('has-sugg', showSugg);
  }, [showSugg]);

  return (
    <div class="side">
      <header class="top">
        <div>
          <p class="mark">Moira</p>
          <Scope />
        </div>
        <div class="seg tabs" role="tablist" aria-label="View">
          <button
            type="button"
            class="press"
            role="tab"
            aria-selected={tab.value === 'ask'}
            onClick={() => {
              tab.value = 'ask';
              settingsOpen.value = false;
            }}
          >
            Ask
          </button>
          <button
            type="button"
            class="press"
            role="tab"
            aria-selected={tab.value === 'recent'}
            onClick={() => {
              tab.value = 'recent';
              settingsOpen.value = false;
            }}
          >
            Recent
          </button>
        </div>
        <button
          type="button"
          class="press recent-btn"
          onClick={() => {
            tab.value = 'recent';
            engine()?.deselect();
            panelState.value = 'full';
          }}
        >
          Recent
        </button>
      </header>

      <section ref={panel} class="panel" aria-label="Conversation">
        <div ref={grab} class="grab-zone">
          <div class="grab" aria-hidden="true" />
          <div class="panel-head">
            <h2>{settingsOpen.value ? 'Settings' : tab.value === 'ask' ? 'Your sky' : 'Recent'}</h2>
            <button
              type="button"
              class="close press"
              aria-label="Close"
              style={{ position: 'static' }}
              onClick={() => {
                panelState.value = 'closed';
              }}
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
          </div>
        </div>
        {settingsOpen.value ? (
          <Settings />
        ) : tab.value === 'ask' ? (
          <div class="thread" aria-live="polite">
            <Lately />
            <div class="spacer" />
            {turns.value.length === 0 && (
              <div class="intro">
                <h1>Ask the way you remember it.</h1>
                <p>Vague is fine. Every answer comes with the star it came from.</p>
                {sample && (
                  <ul class="tries">
                    {SUGGESTIONS.map((q) => (
                      <li key={q}>
                        <button type="button" class="try press" onClick={() => ask(q)}>
                          <span>{q}</span>
                          <Arrow />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
            <AskThread />
          </div>
        ) : (
          <Recent
            onOpen={() => {
              if (narrow.value) panelState.value = 'closed';
            }}
          />
        )}
      </section>

      {showSugg && (
        <div class="sugg" aria-label="Try asking">
          {SUGGESTIONS.map((q) => (
            <button type="button" key={q} class="press" onClick={() => ask(q)}>
              {q}
            </button>
          ))}
        </div>
      )}
      <Composer />
    </div>
  );
}
