// Telegram Mini App (§4.3.12). telegram-web-app.js is loaded ONLY inside Telegram (the URL
// hash has tgWebAppData), so the plain web app works where telegram.org is blocked.

interface TgWebApp {
  initData: string;
  ready(): void;
  expand(): void;
  isVersionAtLeast(v: string): boolean;
  disableVerticalSwipes?: () => void;
  BackButton: {
    show(): void;
    hide(): void;
    onClick(cb: () => void): void;
    offClick(cb: () => void): void;
  };
  HapticFeedback?: { selectionChanged(): void; impactOccurred(s: 'light' | 'medium'): void };
  contentSafeAreaInset?: { top: number; bottom: number; left: number; right: number };
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TgWebApp };
  }
}

export function isTelegram(): boolean {
  return location.hash.includes('tgWebAppData') || !!window.Telegram?.WebApp?.initData;
}

export function webApp(): TgWebApp | null {
  return window.Telegram?.WebApp ?? null;
}

export function initData(): string | null {
  return webApp()?.initData || null;
}

export async function loadTelegram(): Promise<void> {
  if (!location.hash.includes('tgWebAppData')) return;
  await new Promise<void>((resolve) => {
    const s = document.createElement('script');
    s.src = 'https://telegram.org/js/telegram-web-app.js';
    s.onload = () => resolve();
    s.onerror = () => resolve();
    document.head.appendChild(s);
  });
  const app = webApp();
  if (!app) return;
  app.ready();
  app.expand();
  if (app.isVersionAtLeast('7.7')) app.disableVerticalSwipes?.();
  const inset = app.contentSafeAreaInset;
  if (inset) {
    const root = document.documentElement.style;
    root.setProperty('--tg-top', `${inset.top}px`);
    root.setProperty('--tg-bottom', `${inset.bottom}px`);
  }
}

let back: (() => void) | null = null;

/** Show Telegram's BackButton while a sheet or card is open; it closes them. */
export function setBack(handler: (() => void) | null): void {
  const app = webApp();
  if (!app) return;
  if (back) app.BackButton.offClick(back);
  back = handler;
  if (handler) {
    app.BackButton.onClick(handler);
    app.BackButton.show();
  } else {
    app.BackButton.hide();
  }
}
