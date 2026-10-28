// The sky window (§4.3.3): the canvas, the matches pill, zoom, the timeline, toasts and the card.

import { useEffect, useRef } from 'preact/hooks';

import type { SkyPayload } from '../api/types';
import { haptic } from '../lib/haptics';
import { bridge, domLayout, engine, setEngine } from '../sky/engine';
import { SkyEngine } from '../sky/renderer';
import { lit, selected, sky, why } from '../state/sky';
import { narrow, panelState } from '../state/ui';
import { Card } from './Card';
import { MatchesPill } from './MatchesPill';
import { Timeline } from './Timeline';
import { Toast } from './Toast';
import { ZoomControls } from './ZoomControls';

export function SkyWindow({
  payload,
  now,
  interactive = true,
  label = 'Your memories as a night sky. Each star is one memory, coloured by its age from blue-white for new to amber for old, and grouped into named constellations by topic.',
}: {
  payload: SkyPayload | null;
  now?: number;
  interactive?: boolean;
  label?: string;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const first = useRef(true);

  useEffect(() => {
    const c = canvas.current;
    if (!c) return;
    const e = new SkyEngine(c, domLayout(c), {
      onSelect: (id) => {
        selected.value = id;
        if (!id) why.value = '';
        if (id) haptic('select');
        if (id && narrow.value) panelState.value = 'closed';
      },
      onMid: (id) => bridge.bloom(id),
      onEmptyTap: () => {
        const en = engine();
        if (en?.sel) en.deselect();
        else if (lit.value) {
          lit.value = null;
          en?.clearLight();
        }
        if (narrow.value) panelState.value = 'closed';
      },
      onLanded: () => haptic('impact'),
    });
    setEngine(e);
    e.resize();
    const ro = new ResizeObserver(() => e.resize());
    ro.observe(c);
    return () => {
      ro.disconnect();
      e.destroy();
      setEngine(null);
    };
  }, []);

  useEffect(() => {
    const e = engine();
    if (!e || !payload) return;
    e.setData(payload, now ?? payload.template_now ?? Date.now(), first.current);
    first.current = false;
    // Re-render dependents that read the model (timeline, lately).
    sky.value = sky.value === payload ? payload : sky.value;
  }, [payload, now]);

  return (
    <main class="skywin">
      <canvas ref={canvas} class="sky-canvas" role="img" aria-label={label} />
      {interactive && <MatchesPill />}
      {interactive && (
        <ZoomControls
          onFit={() => {
            engine()?.deselect();
            engine()?.fit();
          }}
        />
      )}
      <Timeline />
      <Toast />
      {interactive && <Card />}
    </main>
  );
}
