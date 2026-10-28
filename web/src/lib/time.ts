// Dates in the user's time zone from /api/me (sandboxes: Asia/Kathmandu), never the browser's
// (App. N.4). The server computes the card's strings; lists format `t` here.

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const DAY = 86_400_000;

export interface Parts {
  y: number;
  m: number;
  d: number;
  wd: string;
  h: number;
  min: number;
}

const cache = new Map<string, Intl.DateTimeFormat>();
function fmt(tz: string): Intl.DateTimeFormat {
  let f = cache.get(tz);
  if (!f) {
    f = new Intl.DateTimeFormat('en-GB', {
      timeZone: tz,
      year: 'numeric',
      month: 'numeric',
      day: 'numeric',
      weekday: 'short',
      hour: 'numeric',
      minute: 'numeric',
      hourCycle: 'h23',
    });
    cache.set(tz, f);
  }
  return f;
}

export function parts(t: number, tz: string): Parts {
  const p: Record<string, string> = {};
  for (const x of fmt(tz).formatToParts(new Date(t))) p[x.type] = x.value;
  return {
    y: Number(p.year),
    m: Number(p.month) - 1,
    d: Number(p.day),
    wd: p.weekday ?? '',
    h: Number(p.hour),
    min: Number(p.minute),
  };
}

function dayKey(p: Parts): number {
  return Date.UTC(p.y, p.m, p.d);
}

export function time12(t: number, tz: string): string {
  const p = parts(t, tz);
  const h = p.h % 12 || 12;
  return `${h}:${String(p.min).padStart(2, '0')} ${p.h < 12 ? 'am' : 'pm'}`;
}

/** '12 Oct', with the year when it is not the current year. */
export function short(t: number, tz: string, now: number): string {
  const p = parts(t, tz);
  const year = p.y !== parts(now, tz).y ? ` ${p.y}` : '';
  return `${p.d} ${MON[p.m]}${year}`;
}

export function dayFull(t: number, tz: string): string {
  const p = parts(t, tz);
  return `${p.d} ${MON[p.m]} ${p.y}`;
}

export function longDay(t: number, tz: string): string {
  const p = parts(t, tz);
  const months = [
    'January',
    'February',
    'March',
    'April',
    'May',
    'June',
    'July',
    'August',
    'September',
    'October',
    'November',
    'December',
  ];
  return `${p.d} ${months[p.m]} ${p.y}`;
}

/** Recent list day headers: 'Today', 'Yesterday', 'Sat 24 Oct'. */
export function dayLabel(t: number, tz: string, now: number): string {
  const diff = Math.round((dayKey(parts(now, tz)) - dayKey(parts(t, tz))) / DAY);
  if (diff === 0) return 'Today';
  if (diff === 1) return 'Yesterday';
  const p = parts(t, tz);
  const year = p.y !== parts(now, tz).y ? ` ${p.y}` : '';
  return `${p.wd} ${p.d} ${MON[p.m]}${year}`;
}

/** 'just now', '25 min ago', 'an hour ago', 'Yesterday', '3 days ago', '2 weeks ago', 'Sat 24 Oct' rules. */
export function relative(t: number, tz: string, now: number): string {
  const diff = now - t;
  if (diff < 60_000) return 'just now';
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 60) return `${minutes} min ago`;
  const days = Math.round((dayKey(parts(now, tz)) - dayKey(parts(t, tz))) / DAY);
  if (days === 0) {
    const h = Math.floor(minutes / 60);
    return h === 1 ? 'an hour ago' : `${h} hours ago`;
  }
  if (days === 1) return 'Yesterday';
  if (days < 7) return `${days} days ago`;
  if (days < 14) return 'a week ago';
  if (days < 31) return `${Math.floor(days / 7)} weeks ago`;
  if (days < 60) return 'a month ago';
  if (days < 365) return `${Math.floor(days / 30)} months ago`;
  return days < 730 ? 'a year ago' : `${Math.floor(days / 365)} years ago`;
}

export const MONTHS = MON;
export const DAY_MS = DAY;
