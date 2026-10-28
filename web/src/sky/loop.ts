// Render on demand (§4.3.4): draw only while something moves. When idle, twinkle at 24 fps,
// 12 fps after 20 s; stop when the tab is hidden or reduced motion is on.

export class Loop {
  private on = false;
  private stopped = false;
  private lastActive = 0;
  private idle = 0;

  constructor(
    private readonly frame: (now: number) => boolean,
    private readonly reduced: () => boolean,
  ) {}

  wake(): void {
    if (this.stopped) return;
    this.lastActive = performance.now();
    clearTimeout(this.idle);
    this.schedule();
  }

  stop(): void {
    this.stopped = true;
    clearTimeout(this.idle);
  }

  private schedule(): void {
    if (this.on || this.stopped) return;
    this.on = true;
    requestAnimationFrame((now) => this.tick(now));
  }

  private tick(now: number): void {
    this.on = false;
    if (document.hidden || this.stopped) return;
    const busy = this.frame(now);
    if (busy) {
      this.lastActive = now;
      this.schedule();
      return;
    }
    if (this.reduced()) return;
    clearTimeout(this.idle);
    this.idle = window.setTimeout(() => this.schedule(), now - this.lastActive > 20_000 ? 83 : 41);
  }
}
