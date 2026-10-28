// Server-sent events over fetch (EventSource cannot POST). Handles events split across chunks.

export interface SseFrame {
  event: string;
  data: unknown;
}

export class SseParser {
  private buf = '';

  constructor(private readonly onFrame: (f: SseFrame) => void) {}

  push(chunk: string): void {
    this.buf += chunk.replace(/\r\n/g, '\n');
    let i: number;
    while ((i = this.buf.indexOf('\n\n')) >= 0) {
      const raw = this.buf.slice(0, i);
      this.buf = this.buf.slice(i + 2);
      const frame = parseFrame(raw);
      if (frame) this.onFrame(frame);
    }
  }
}

export function parseFrame(raw: string): SseFrame | null {
  let event = 'message';
  const data: string[] = [];
  for (const line of raw.split('\n')) {
    if (!line || line.startsWith(':')) continue;
    const idx = line.indexOf(':');
    const field = idx < 0 ? line : line.slice(0, idx);
    const value = idx < 0 ? '' : line.slice(idx + 1).replace(/^ /, '');
    if (field === 'event') event = value;
    else if (field === 'data') data.push(value);
  }
  if (!data.length) return null;
  const text = data.join('\n');
  try {
    return { event, data: JSON.parse(text) };
  } catch {
    return { event, data: text };
  }
}

/** Read a streaming Response body and call onFrame for every complete event. */
export async function readSse(res: Response, onFrame: (f: SseFrame) => void): Promise<void> {
  if (!res.body) return;
  const parser = new SseParser(onFrame);
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    parser.push(value);
  }
}
