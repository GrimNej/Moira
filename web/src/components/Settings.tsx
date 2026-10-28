// Settings (§4.3.2): time zone, usage and credits, export, sessions, privacy, forget everything.

import { useState } from 'preact/hooks';

import { api, request } from '../api/client';
import { me, signOut } from '../state/session';
import { showToast } from '../state/ui';

const ZONES = [
  'Asia/Kathmandu',
  'Asia/Kolkata',
  'Europe/London',
  'Europe/Berlin',
  'America/New_York',
  'America/Los_Angeles',
  'Asia/Tokyo',
  'Australia/Sydney',
  'UTC',
];

export function Settings() {
  const user = me.value;
  const [forgetAt, setForgetAt] = useState<number | null>(null);
  if (!user) return null;
  const sandbox = user.kind === 'sandbox';
  const zones = ZONES.includes(user.tz) ? ZONES : [user.tz, ...ZONES];
  return (
    <div class="settings">
      <h2>Time zone</h2>
      <p>Dates in answers and lists use this zone.</p>
      <select
        aria-label="Time zone"
        value={user.tz}
        onChange={async (e) => {
          me.value = await api.setTz((e.target as HTMLSelectElement).value);
          showToast('Time zone saved');
        }}
      >
        {zones.map((z) => (
          <option key={z} value={z}>
            {z}
          </option>
        ))}
      </select>

      <h2>Usage today</h2>
      <p class="num">
        ${user.caps.spent_today.toFixed(2)} of ${user.caps.cap_today.toFixed(2)} for AI today.
        Saving and instant search never stop when the limit is reached.
      </p>

      {!sandbox && (
        <>
          <h2>Export</h2>
          <p>Everything you saved, as JSONL, Markdown and your SQLite file.</p>
          <a
            class="secondary-btn press"
            href="/api/export"
            download
            style={{ display: 'inline-flex', alignItems: 'center', textDecoration: 'none' }}
          >
            Download export
          </a>
        </>
      )}

      <h2>Sessions</h2>
      <div class="actions">
        <button
          type="button"
          class="press"
          onClick={async () => {
            await api.logoutOthers();
            showToast('Signed out everywhere else');
          }}
        >
          Sign out other sessions
        </button>
        <button type="button" class="press" onClick={() => void signOut()}>
          Sign out
        </button>
      </div>

      <h2>Privacy</h2>
      <p>
        Moira keeps the text of what you send. Passwords and card numbers are hidden before anything
        is stored. Images, audio and video are read into text and deleted. Text is sent to Meta’s
        model in Standard mode, which does not train on it, and every request asks Meta not to keep
        it.
      </p>

      {!sandbox && (
        <>
          <h2>Forget everything</h2>
          {forgetAt ? (
            <>
              <p>Everything will be deleted in 24 hours. You can cancel until then.</p>
              <button
                type="button"
                class="secondary-btn press"
                onClick={async () => {
                  await request('DELETE', '/api/forget-everything');
                  setForgetAt(null);
                  showToast('Cancelled');
                }}
              >
                Cancel
              </button>
            </>
          ) : (
            <>
              <p>Deletes your whole memory after a 24-hour grace period.</p>
              <button
                type="button"
                class="secondary-btn press"
                onClick={async () => {
                  const r = await request<{ scheduled_for: number }>(
                    'POST',
                    '/api/forget-everything',
                  );
                  setForgetAt(r.scheduled_for);
                }}
              >
                Forget everything
              </button>
            </>
          )}
        </>
      )}
      <p class="note num">Version {user.version}</p>
    </div>
  );
}
