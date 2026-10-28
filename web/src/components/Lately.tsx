// Saved lately (§4.3.7): the 4 newest memories at the top of the empty Ask column.

import { relative } from '../lib/time';
import { engine } from '../sky/engine';
import { ageCss } from '../sky/palette';
import { tz } from '../state/session';
import { sky } from '../state/sky';

export function Lately() {
  const p = sky.value;
  if (!p || !p.stars.id.length) return null;
  const now = engine()?.model?.now ?? Date.now();
  const idx = p.stars.t
    .map((t, i) => [t, i] as const)
    .sort((a, b) => b[0] - a[0])
    .slice(0, 4);
  return (
    <div class="lately">
      <h4>Saved lately</h4>
      {idx.map(([t, i]) => (
        <button
          type="button"
          key={p.stars.id[i]}
          class="row press"
          onClick={() => engine()?.select(p.stars.id[i]!)}
        >
          <span class="dot" style={{ '--c': ageCss(t, now) }} />
          <span class="t">{p.stars.title[i]}</span>
          <span class="m num">{relative(t, tz.value, now)}</span>
        </button>
      ))}
    </div>
  );
}
