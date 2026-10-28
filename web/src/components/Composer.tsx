// The composer (§4.3.8): one pill with Ask | Save, the input (16 px, so iOS does not zoom), the
// send button, and in Save mode one + for a voice note or a screenshot.

import { useRef, useState } from 'preact/hooks';

import { askQuestion, saveFiles, saveNugget, saveVoice } from '../actions';
import { canRecord, startRecording, type Recording } from '../lib/recorder';
import { waiting } from '../state/capture';
import { mode, showToast } from '../state/ui';

export function Composer() {
  const input = useRef<HTMLInputElement>(null);
  const file = useRef<HTMLInputElement>(null);
  const [text, setText] = useState('');
  const [rec, setRec] = useState<Recording | null>(null);
  const [menu, setMenu] = useState(false);
  const m = mode.value;

  const setMode = (next: 'ask' | 'save'): void => {
    mode.value = next;
    input.current?.focus();
  };

  async function voice(): Promise<void> {
    if (rec) {
      const blob = await rec.stop();
      setRec(null);
      await saveVoice(blob);
      return;
    }
    if (!canRecord()) {
      showToast('Send a voice note to the bot instead');
      return;
    }
    try {
      setRec(await startRecording());
    } catch {
      showToast('Send a voice note to the bot instead');
    }
  }

  return (
    <form
      class="composer"
      autocomplete="off"
      onSubmit={(e) => {
        e.preventDefault();
        const v = text.trim();
        if (!v) return;
        setText('');
        if (m === 'ask') void askQuestion(v);
        else void saveNugget(v);
      }}
      onPaste={(e) => {
        if (m !== 'save') return;
        const files = [...(e.clipboardData?.files ?? [])].filter((f) =>
          f.type.startsWith('image/'),
        );
        if (files.length) {
          e.preventDefault();
          void saveFiles(files.slice(0, 10));
        }
      }}
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        const files = [...(e.dataTransfer?.files ?? [])].filter((f) => f.type.startsWith('image/'));
        if (files.length) {
          e.preventDefault();
          void saveFiles(files.slice(0, 10));
        }
      }}
    >
      <div class="seg" role="tablist" aria-label="What the box does">
        <button
          type="button"
          class="press"
          role="tab"
          aria-selected={m === 'ask'}
          onClick={() => setMode('ask')}
        >
          Ask
        </button>
        <button
          type="button"
          class="press"
          role="tab"
          aria-selected={m === 'save'}
          onClick={() => setMode('save')}
        >
          Save
        </button>
      </div>
      <input
        ref={input}
        id="q"
        name="q"
        enterkeyhint="send"
        placeholder={m === 'ask' ? 'Ask anything you saved' : 'Save anything'}
        aria-label={m === 'ask' ? 'Ask your sky' : 'Save something'}
        value={text}
        onInput={(e) => setText((e.target as HTMLInputElement).value)}
      />
      {waiting.value > 0 && <span class="waiting num">{waiting.value} waiting to send</span>}
      {m === 'save' && (
        <>
          <input
            ref={file}
            type="file"
            accept="image/*"
            multiple
            hidden
            onChange={(e) => {
              const files = [...((e.target as HTMLInputElement).files ?? [])].slice(0, 10);
              if (files.length) void saveFiles(files);
              (e.target as HTMLInputElement).value = '';
            }}
          />
          <button
            type="button"
            class="ibtn press"
            aria-label={rec ? 'Stop and save the voice note' : 'Add a voice note or a screenshot'}
            aria-expanded={menu}
            onClick={() => {
              if (rec) void voice();
              else setMenu(!menu);
            }}
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
              stroke-linecap="round"
            >
              {rec ? (
                <rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor" />
              ) : (
                <path d="M12 5v14M5 12h14" />
              )}
            </svg>
          </button>
          {menu && !rec && (
            <div class="add-menu" role="menu">
              <button
                type="button"
                role="menuitem"
                class="press"
                onClick={() => {
                  setMenu(false);
                  void voice();
                }}
              >
                Voice note
              </button>
              <button
                type="button"
                role="menuitem"
                class="press"
                onClick={() => {
                  setMenu(false);
                  file.current?.click();
                }}
              >
                Screenshot
              </button>
            </div>
          )}
        </>
      )}
      <button class="send press" type="submit" aria-label="Send" disabled={!text.trim()}>
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2.2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <path d="M12 19V5M6 11l6-6 6 6" />
        </svg>
      </button>
    </form>
  );
}
