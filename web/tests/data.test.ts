import { describe, expect, it } from 'vitest';

import { headers, setBearer } from '../src/api/client';
import { parseFrame, SseParser, type SseFrame } from '../src/api/sse';
import { dayLabel, relative, short, time12 } from '../src/lib/time';
import { parseRoute } from '../src/router';

const TZ = 'Asia/Kathmandu';
// Mon 26 Oct 2026, 21:00 in Kathmandu (UTC+05:45)
const NOW = Date.UTC(2026, 9, 26, 15, 15);
const H = 3_600_000;

describe('SSE parser', () => {
  it('handles events split across chunks', () => {
    const got: SseFrame[] = [];
    const p = new SseParser((f) => got.push(f));
    p.push('event: clues\ndata: {"terms"');
    p.push(':["ai"]}\n');
    p.push('\nevent: done\nda');
    p.push('ta: {}\n\n');
    expect(got).toEqual([
      { event: 'clues', data: { terms: ['ai'] } },
      { event: 'done', data: {} },
    ]);
  });

  it('ignores comments and joins multi-line data', () => {
    expect(parseFrame(': ping\nevent: x\ndata: a\ndata: b')).toEqual({ event: 'x', data: 'a\nb' });
    expect(parseFrame(': only a comment')).toBeNull();
  });

  it('accepts CRLF', () => {
    const got: SseFrame[] = [];
    new SseParser((f) => got.push(f)).push('event: ping\r\ndata: {}\r\n\r\n');
    expect(got).toEqual([{ event: 'ping', data: {} }]);
  });
});

describe('client', () => {
  it('adds X-Moira to every write and never to reads', () => {
    expect(headers('POST')['X-Moira']).toBe('1');
    expect(headers('PATCH')['X-Moira']).toBe('1');
    expect(headers('DELETE')['X-Moira']).toBe('1');
    expect(headers('GET')['X-Moira']).toBeUndefined();
  });

  it('sends the bearer token when the Mini App has one', () => {
    setBearer('tok');
    expect(headers('GET').Authorization).toBe('Bearer tok');
    setBearer(null);
    expect(headers('GET').Authorization).toBeUndefined();
  });
});

describe('time formatting in the user zone', () => {
  it('follows the App. N.4 rules', () => {
    expect(relative(NOW - 30_000, TZ, NOW)).toBe('just now');
    expect(relative(NOW - 25 * 60_000, TZ, NOW)).toBe('25 min ago');
    expect(relative(NOW - 1.2 * H, TZ, NOW)).toBe('an hour ago');
    expect(relative(NOW - 24 * H, TZ, NOW)).toBe('Yesterday');
    expect(relative(NOW - 3 * 24 * H, TZ, NOW)).toBe('3 days ago');
    expect(relative(NOW - 14 * 24 * H, TZ, NOW)).toBe('2 weeks ago');
  });

  it('labels days in the user zone, not the browser zone', () => {
    // 20:00 UTC on 25 Oct is already 01:45 on 26 Oct in Kathmandu: "Today".
    expect(dayLabel(Date.UTC(2026, 9, 25, 20, 0), TZ, NOW)).toBe('Today');
    expect(dayLabel(Date.UTC(2026, 9, 24, 12, 0), TZ, NOW)).toBe('Sat 24 Oct');
    expect(dayLabel(NOW - 24 * H, TZ, NOW)).toBe('Yesterday');
  });

  it('formats short dates and times', () => {
    expect(short(Date.UTC(2026, 9, 12, 15, 55), TZ, NOW)).toBe('12 Oct');
    expect(short(Date.UTC(2025, 2, 2, 12), TZ, NOW)).toBe('2 Mar 2025');
    expect(time12(Date.UTC(2026, 9, 12, 15, 55), TZ)).toBe('9:40 pm');
  });
});

describe('router', () => {
  it('parses every route', () => {
    expect(parseRoute('/', '?star=n_abc&from=tg', '')).toEqual({
      name: 'home',
      star: 'n_abc',
      from: 'tg',
      saved: null,
    });
    expect(parseRoute('/n/n_xyz', '', '')).toMatchObject({ name: 'home', star: 'n_xyz' });
    expect(parseRoute('/recent', '', '')).toEqual({ name: 'recent' });
    expect(parseRoute('/login', '', '#t=TOKEN')).toEqual({ name: 'login', token: 'TOKEN' });
    expect(parseRoute('/settings', '', '')).toEqual({ name: 'settings' });
  });
});
