// Focus management (§4.3.13): opening a card or sheet moves focus to its title; closing
// returns focus to the control that opened it.

let returnTo: HTMLElement | null = null;

export function rememberFocus(): void {
  const el = document.activeElement;
  returnTo = el instanceof HTMLElement && el !== document.body ? el : null;
}

export function focusTitle(container: HTMLElement | null): void {
  const title = container?.querySelector<HTMLElement>('h2, [data-title]');
  if (title) {
    title.setAttribute('tabindex', '-1');
    title.focus({ preventScroll: true });
  }
}

export function restoreFocus(): void {
  if (returnTo && document.contains(returnTo)) returnTo.focus({ preventScroll: true });
  returnTo = null;
}
