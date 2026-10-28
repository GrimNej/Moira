// Telegram haptics: a selection tick on star select, a light impact when a saved star lands.

import { webApp } from './telegram';

export function haptic(kind: 'select' | 'impact'): void {
  try {
    const h = webApp()?.HapticFeedback;
    if (!h) return;
    if (kind === 'select') h.selectionChanged();
    else h.impactOccurred('light');
  } catch {
    // Older clients: no haptics.
  }
}
