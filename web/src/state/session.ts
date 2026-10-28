// Who is signed in. Inside Telegram the Mini App signs in automatically (§4.3.12).

import { computed, signal } from '@preact/signals';

import { api, ApiError, setBearer } from '../api/client';
import type { Me } from '../api/types';
import { initData, isTelegram } from '../lib/telegram';

export const me = signal<Me | null>(null);
export const booted = signal(false);
export const tz = computed(() => me.value?.tz ?? 'Asia/Kathmandu');
export const isSample = computed(() => me.value?.kind === 'sandbox' || me.value?.kind === 'judge');

export async function boot(): Promise<void> {
  try {
    if (isTelegram()) {
      const data = initData();
      if (data) {
        const res = await api.telegram(data);
        setBearer(res.bearer);
        me.value = res.user;
        return;
      }
    }
    me.value = await api.me();
  } catch (e) {
    if (!(e instanceof ApiError) || e.status !== 401) console.warn('sign-in check failed');
    me.value = null;
  } finally {
    booted.value = true;
  }
}

export async function startSandbox(): Promise<void> {
  const res = await api.sandbox();
  me.value = res.user;
}

export async function signOut(): Promise<void> {
  await api.logout().catch(() => undefined);
  setBearer(null);
  me.value = null;
}
