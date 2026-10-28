// End-to-end on phone and desktop with the API mocked from the sample memory (FakeLLM-built).

import { expect, test, type Page } from '@playwright/test';

interface Sky {
  template_now: number;
  stars: {
    id: string[];
    t: number[];
    title: string[];
    kind: string[];
    source: string[];
    hub: string[];
  };
  hubs: { id: string; name: string }[];
}

let sky: Sky;
const me = {
  id: 'u_sample',
  kind: 'sandbox',
  display_name: 'Sample',
  tz: 'Asia/Kathmandu',
  caps: { spent_today: 0, cap_today: 0.1 },
  version: '0.5.0',
};

test.beforeAll(async ({ request }) => {
  sky = (await (await request.get('/welcome-sky.json')).json()) as Sky;
});

function recent() {
  const s = sky.stars;
  const idx = s.id
    .map((_, i) => i)
    .sort((a, b) => s.t[b]! - s.t[a]!)
    .slice(0, 30);
  return {
    items: idx.map((i) => ({
      id: s.id[i],
      title: s.title[i],
      kind: s.kind[i],
      source: s.source[i],
      hub: { id: s.hub[i], name: sky.hubs.find((h) => h.id === s.hub[i])?.name ?? '' },
      t: s.t[i],
    })),
    next_cursor: null,
  };
}

async function signedIn(page: Page): Promise<void> {
  await page.route('**/api/me', (r) => r.fulfill({ json: me }));
  await page.route('**/api/sky*', (r) => r.fulfill({ json: sky }));
  await page.route('**/api/recent*', (r) => r.fulfill({ json: recent() }));
  await page.route('**/api/events', (r) => r.fulfill({ status: 204, body: '' }));
  await page.route('**/api/ask', (r) => {
    const top = sky.stars.id[0]!;
    const frames = [
      ['clues', { source: null, time_label: null, terms: ['fruit'], intent: 'lookup' }],
      ['lit', { ids: [top], top }],
      [
        'answer',
        {
          answer: 'Mango, by a long way.',
          citations: [{ id: top, why: 'you said so' }],
          also: [],
          confidence: 'high',
          tier: 'answer',
          turn_id: 1,
        },
      ],
      ['done', {}],
    ];
    const body = frames.map(([e, d]) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`).join('');
    return r.fulfill({ headers: { 'Content-Type': 'text/event-stream' }, body });
  });
}

async function skyPainted(page: Page): Promise<number> {
  return page.locator('canvas.sky-canvas').evaluate((c: HTMLCanvasElement) => {
    const ctx = c.getContext('2d')!;
    const d = ctx.getImageData(0, 0, c.width, c.height).data;
    let lit = 0;
    for (let i = 0; i < d.length; i += 4 * 97) if (d[i]! + d[i + 1]! + d[i + 2]! > 120) lit++;
    return lit;
  });
}

test('welcome draws the sample sky without signing in', async ({ page }, info) => {
  await page.route('**/api/me', (r) =>
    r.fulfill({ status: 401, json: { error: { code: 'unauthorized', message: 'Sign in' } } }),
  );
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Try the sample memory' })).toBeVisible();
  await expect.poll(() => skyPainted(page), { timeout: 10_000 }).toBeGreaterThan(5);
  await page.screenshot({ path: `../docs/media/welcome-${info.project.name}.png` });
});

test('the sky window follows the layout of §4.3.3', async ({ page }, info) => {
  await signedIn(page);
  await page.goto('/');
  const win = page.locator('main.skywin');
  await expect(win).toBeVisible();
  const box = (await win.boundingBox())!;
  const vp = page.viewportSize()!;
  expect(await win.evaluate((el) => getComputedStyle(el).backgroundColor)).toBe('rgb(0, 0, 0)');
  if (vp.width >= 900) {
    expect(box.x).toBeGreaterThanOrEqual(384);
    expect(Math.round(vp.width - (box.x + box.width))).toBe(10);
    expect(Math.round(box.y)).toBe(10);
  } else {
    expect(Math.round(box.x)).toBe(0);
    expect(Math.round(box.width)).toBe(vp.width);
  }
  await expect.poll(() => skyPainted(page), { timeout: 10_000 }).toBeGreaterThan(5);
  await page.waitForTimeout(1200); // let the first fly-in settle
  await page.screenshot({ path: `../docs/media/sky-${info.project.name}.png` });
});

test('asking streams an answer with its source', async ({ page }, info) => {
  await signedIn(page);
  await page.goto('/');
  const q = page.locator('#q');
  await q.fill('what’s my favorite fruit?');
  await q.press('Enter');
  await expect(page.getByText('Mango, by a long way.')).toBeVisible();
  await page.waitForTimeout(900);
  await page.screenshot({ path: `../docs/media/answer-${info.project.name}.png` });
});

test('Recent lists memories newest first', async ({ page }) => {
  await signedIn(page);
  await page.goto('/recent');
  const first = recent().items[0]!.title!;
  await expect(page.locator('#rlist .rrow').first()).toContainText(first.slice(0, 20));
});

function withNewStar(id: string) {
  const s = sky.stars as unknown as Record<string, unknown[]>;
  const stars = Object.fromEntries(Object.entries(s).map(([k, v]) => [k, [...v, v[0]]]));
  (stars.id as string[])[stars.id!.length - 1] = id;
  (stars.title as string[])[stars.title!.length - 1] = 'buy oat milk';
  (stars.t as number[])[stars.t!.length - 1] = sky.template_now;
  return { ...sky, stars, cursor: 'c2', removed: [] };
}

test('save → comet → star → toast Undo removes it', async ({ page }) => {
  await signedIn(page);
  let saved: () => void = () => undefined;
  const filed = new Promise<void>((r) => (saved = r));
  let first = true;
  await page.route('**/api/events', async (r) => {
    if (!first) return r.fulfill({ status: 204, body: '' });
    first = false;
    await filed;
    const hub = sky.hubs[0]!;
    const data = { id: 'n_new', hub_id: hub.id, hub_name: hub.name, fact_changed: false, now: [] };
    return r.fulfill({
      headers: { 'Content-Type': 'text/event-stream' },
      body: `event: filed\ndata: ${JSON.stringify(data)}\n\n`,
    });
  });
  await page.route('**/api/nuggets', (r) => {
    saved();
    return r.fulfill({ status: 202, json: { id: 'n_new', status: 'filing' } });
  });
  await page.route(
    (u) => u.pathname === '/api/sky' && u.searchParams.has('since'),
    (r) => r.fulfill({ json: withNewStar('n_new') }),
  );
  let forgot = false;
  await page.route('**/api/nuggets/n_new/forget', (r) => {
    forgot = true;
    return r.fulfill({ json: { undo_group_id: 'g', undo_until: 0 } });
  });

  await page.goto('/');
  await page.getByRole('tab', { name: 'Save', exact: true }).click();
  await page.locator('#q').fill('buy oat milk');
  await page.locator('#q').press('Enter');
  const toast = page.getByRole('status').filter({ hasText: `Filed in ${sky.hubs[0]!.name}` });
  await expect(toast).toBeVisible({ timeout: 10_000 });
  await toast.getByRole('button', { name: 'Undo' }).click();
  await expect.poll(() => forgot).toBe(true);
});

test('offline saves queue and send on reconnect', async ({ page, context }) => {
  await signedIn(page);
  const sent: string[] = [];
  await page.route('**/api/nuggets', async (r) => {
    sent.push((r.request().postDataJSON() as { text: string }).text);
    return r.fulfill({ status: 202, json: { id: 'n_off', status: 'filing' } });
  });
  await page.goto('/');
  await page.getByRole('tab', { name: 'Save', exact: true }).click();
  await context.setOffline(true);
  await page.locator('#q').fill('call the dentist');
  await page.locator('#q').press('Enter');
  await expect(page.getByText('Saved offline', { exact: false })).toBeVisible();
  expect(sent).toEqual([]);
  await context.setOffline(false);
  await expect.poll(() => sent).toEqual(['call the dentist']);
});
