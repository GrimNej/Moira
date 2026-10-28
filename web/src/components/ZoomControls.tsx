// Zoom in, out and fit (top right of the window; slides left of the open card).

import { engine } from '../sky/engine';

export function ZoomControls({ onFit }: { onFit: () => void }) {
  return (
    <div class="zoom" role="group" aria-label="Zoom">
      <button
        type="button"
        class="press"
        aria-label="Zoom in"
        onClick={() => engine()?.zoomBy(1.8)}
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.8"
          stroke-linecap="round"
        >
          <path d="M12 5v14M5 12h14" />
        </svg>
      </button>
      <button
        type="button"
        class="press"
        aria-label="Zoom out"
        onClick={() => engine()?.zoomBy(1 / 1.8)}
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.8"
          stroke-linecap="round"
        >
          <path d="M5 12h14" />
        </svg>
      </button>
      <button type="button" class="press" aria-label="Show the whole sky" onClick={onFit}>
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.8"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" />
        </svg>
      </button>
    </div>
  );
}
