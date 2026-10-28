// Welcome (§4.3.2): the sample sky in the window, one line, Try the sample memory, Sign in.
// The sky comes from a static welcome-sky.json, so no sign-in is needed to draw it.

import { useEffect, useState } from 'preact/hooks';

import type { SkyPayload } from '../api/types';
import { startSandbox } from '../state/session';
import { SkyWindow } from './SkyWindow';

export function Welcome({ onStarted }: { onStarted: () => void }) {
  const [payload, setPayload] = useState<SkyPayload | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [howTo, setHowTo] = useState(false);

  useEffect(() => {
    fetch('/welcome-sky.json')
      .then((r) => (r.ok ? (r.json() as Promise<SkyPayload>) : null))
      .then(setPayload)
      .catch(() => setPayload(null));
  }, []);

  return (
    <>
      <div class="side">
        <header class="top">
          <div>
            <p class="mark">Moira</p>
            <span class="scope">A memory you text</span>
          </div>
        </header>
        <div class="panel welcome">
          <div class="thread">
            <div class="spacer" />
            <div class="intro" style={{ display: 'block' }}>
              <h1>Everything you save becomes a star.</h1>
              <p>Ask the way you remember it.</p>
              <div class="welcome-actions">
                <button
                  type="button"
                  class="primary-btn press"
                  disabled={busy}
                  onClick={async () => {
                    setBusy(true);
                    setError('');
                    try {
                      await startSandbox();
                      onStarted();
                    } catch {
                      setError('Couldn’t start the sample memory. Try again in a minute.');
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  {busy ? 'Starting…' : 'Try the sample memory'}
                </button>
                <button type="button" class="secondary-btn press" onClick={() => setHowTo(!howTo)}>
                  Sign in
                </button>
              </div>
              {error && (
                <p class="note" role="status">
                  {error}
                </p>
              )}
              {howTo && (
                <p class="note">
                  Send /web to the Moira bot in Telegram. It replies with a sign-in link that works
                  once, for 10 minutes.
                </p>
              )}
            </div>
          </div>
        </div>
      </div>
      <SkyWindow
        payload={payload}
        now={payload?.template_now}
        interactive={false}
        label="A sample sky. Each star is something a fictional person saved, coloured by its age."
      />
    </>
  );
}
