// Interface state shared between components: tabs, the toast, the phone layout.

import { signal } from '@preact/signals';

export const NARROW = 900;
export const narrow = signal(typeof innerWidth === 'number' ? innerWidth < NARROW : false);
addEventListener('resize', () => {
  narrow.value = innerWidth < NARROW;
});

export const tab = signal<'ask' | 'recent'>('ask');
export const mode = signal<'ask' | 'save'>('ask');
export const asked = signal(false);
export const panelState = signal<'closed' | 'peek' | 'full'>('closed');
export const settingsOpen = signal(false);

export interface ToastState {
  text: string;
  action: { label: string; run: () => void } | null;
  id: number;
}
export const toast = signal<ToastState | null>(null);
let toastSeq = 0;
let timer = 0;

/** Show a toast; with an action (Undo) it stays 6 s, otherwise 2.6 s. */
export function showToast(text: string, action: ToastState['action'] = null): void {
  toast.value = { text, action, id: ++toastSeq };
  clearTimeout(timer);
  timer = window.setTimeout(
    () => {
      toast.value = null;
    },
    action ? 6000 : 2600,
  );
}

export function hideToast(): void {
  clearTimeout(timer);
  toast.value = null;
}
