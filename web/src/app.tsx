// The app shell: Welcome when signed out, the sky with the column when signed in (§4.3.2).

import { useEffect } from 'preact/hooks';

import { startLive, stopLive } from './actions';
import { Column } from './components/Column';
import { Login } from './components/Login';
import { SkyWindow } from './components/SkyWindow';
import { Welcome } from './components/Welcome';
import { navigate, route } from './router';
import { engine } from './sky/engine';
import { booted, me } from './state/session';
import { lit, loadSky, refreshSky, sky, why } from './state/sky';
import { api } from './api/client';
import { narrow, panelState, settingsOpen, showToast, tab } from './state/ui';
import { retryQueue } from './state/capture';

function Main() {
  useEffect(() => {
    void loadSky().then(() => {
      const r = route.value;
      if (r.name === 'home' && r.star) {
        const id = r.star;
        setTimeout(() => {
          if (r.from === 'tg') why.value = '';
          engine()?.select(id);
        }, 900);
      }
      const undo = new URLSearchParams(location.search).get('undo');
      if (undo) {
        // An undo link from the owner's daily digest (§7.9): revert one tidy change.
        history.replaceState(null, '', '/');
        void api
          .undo(undo)
          .then(() => refreshSky())
          .then(() => showToast('Undone'))
          .catch(() => showToast('That change could not be undone.'));
      }
      if (r.name === 'home' && r.saved) {
        // Back from the Android share target (§4.3.12): the star arrives over the live stream.
        showToast('Saved');
        history.replaceState(null, '', '/');
      }
      if (r.name === 'recent') {
        tab.value = 'recent';
        if (narrow.value) panelState.value = 'full';
      }
      if (r.name === 'settings') settingsOpen.value = true;
    });
    startLive();
    void retryQueue();
    return () => stopLive();
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      const t = e.target as HTMLElement;
      const inField = !!t.closest?.('input,textarea,select,[role="slider"]');
      const en = engine();
      if (e.key === 'Escape') {
        if (en?.sel) en.deselect();
        else if (lit.value) {
          lit.value = null;
          en?.clearLight();
        } else if (inField) t.blur();
        return;
      }
      if (inField) return;
      if (e.key === '/') {
        e.preventDefault();
        document.getElementById('q')?.focus();
        return;
      }
      if (en?.keydown(e)) e.preventDefault();
    };
    addEventListener('keydown', onKey);
    return () => removeEventListener('keydown', onKey);
  }, []);

  return (
    <>
      <a
        class="skip"
        href="#rlist"
        onClick={() => {
          tab.value = 'recent';
          if (narrow.value) panelState.value = 'full';
        }}
      >
        Skip to the list of memories
      </a>
      <Column />
      <SkyWindow payload={sky.value} />
    </>
  );
}

export function App() {
  const r = route.value;
  if (r.name === 'login') return <Login token={r.token} />;
  if (!booted.value) return <div class="side" />;
  if (!me.value) return <Welcome onStarted={() => navigate('/', true)} />;
  return <Main />;
}
