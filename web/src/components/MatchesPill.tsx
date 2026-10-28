// "3 matches · Clear" while a search lights the sky (top left of the window).

import { engine } from '../sky/engine';
import { lit } from '../state/sky';

export function MatchesPill() {
  const l = lit.value;
  if (!l || !l.ids.length) return null;
  const n = l.ids.length;
  return (
    <div class="lit">
      <span>{n === 1 ? '1 match' : `${n} matches`}</span>
      <button
        type="button"
        class="press"
        onClick={() => {
          lit.value = null;
          engine()?.clearLight();
        }}
      >
        Clear
      </button>
    </div>
  );
}
