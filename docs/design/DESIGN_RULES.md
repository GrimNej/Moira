# Design rules

For every UI review: the anti-generic rules of blueprint §4.3.11. Each one is a test a reviewer can run on a screenshot.

| Rule | Instead |
|---|---|
| No navy, slate, violet or indigo grounds or tints | True neutral blacks: frame `#0b0b0c`, sky `#000`, surfaces one lightness step up |
| Colour only on data (stars, timeline bars, row dots). Chrome is neutral | The primary action is **inversion**: a white pill with black text |
| No glass, no `backdrop-filter`, no glows on UI | Opaque surfaces one tone step from the ground. (Blur over an animating canvas also costs battery on phones.) |
| No gradients on grounds, buttons, cards or text | Flat fills. The only gradients are scrims over the sky picture (timeline, phone top bar) |
| No monospace anywhere | The UI face with `font-variant-numeric: tabular-nums` for dates and counts |
| No tiny tracked capitals, no eyebrow labels above titles, no middle-dot meta strings | Sentence case at 13 px or more; meta written as words ("AI tools, 12 Oct") |
| Two typefaces, each with one job | Jost for the wordmark, constellation names, card titles, the Now line and the empty-state line; the system UI face for everything else |
| One radius family | Soft: sky window 26, panels and sheets 22–24, blocks 12–18, every control fully round |
| Shadows only on what floats | The card and the sheets; nothing at rest |
| No instruction text about how to use a control | Controls explain themselves; the canvas has an `aria-label`; first-time hints are not needed |
| Every status message is specific | "Looking through 171 memories from around 12 Oct", never "Thinking…" |
| Feedback on pointer-down | Scale 0.97 over 100 ms on every button |
| Motion is interruptible | Flights and sheets start from the live position; touch cancels them |
| Dynamic styles go through the CSS object model | Under the CSP `style-src 'self'` (§13.13), set per-element styles with Preact's `style` prop (for example the row dot's `--c`), never with `style="…"` inside HTML strings |

## Review checklist

- [ ] Every rule above holds on the phone (390 and 360 px) and desktop (1440 px) screenshots
- [ ] Reduced motion checked
- [ ] Keyboard path checked
