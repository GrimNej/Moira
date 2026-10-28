// /login#t=…: the token is read from the fragment and sent by POST, never on GET (§10.2).

import { useEffect, useState } from 'preact/hooks';

import { api } from '../api/client';
import { navigate } from '../router';
import { boot } from '../state/session';

export function Login({ token }: { token: string | null }) {
  const [error, setError] = useState('');
  useEffect(() => {
    history.replaceState(null, '', '/login'); // clear the fragment at once
    if (!token) {
      setError('This sign-in link is incomplete. Send /web to the bot again.');
      return;
    }
    api
      .loginLink(token)
      .then(async () => {
        await boot();
        navigate('/', true);
      })
      .catch(() =>
        setError('This sign-in link has expired or was already used. Send /web to the bot again.'),
      );
  }, [token]);
  return (
    <div class="side">
      <header class="top">
        <div>
          <p class="mark">Moira</p>
          <span class="scope">{error ? 'Sign-in' : 'Signing you in'}</span>
        </div>
      </header>
      {error && (
        <p class="note" role="status">
          {error}
        </p>
      )}
    </div>
  );
}
