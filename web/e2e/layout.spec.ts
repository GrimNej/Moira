import { expect, test } from '@playwright/test';

test('frame and sky window follow the layout of §4.3.3', async ({ page }, info) => {
  await page.goto('/');
  const sky = page.locator('main.window');
  await expect(sky).toBeVisible();
  const box = await sky.boundingBox();
  const viewport = page.viewportSize()!;
  expect(box).not.toBeNull();
  const bg = await sky.evaluate((el) => getComputedStyle(el).backgroundColor);
  expect(bg).toBe('rgb(0, 0, 0)');

  if (viewport.width >= 900) {
    // Desktop: the column on the left, the window inset 10 px with radius 26.
    expect(box!.x).toBeGreaterThanOrEqual(384);
    expect(Math.round(viewport.width - (box!.x + box!.width))).toBe(10);
    expect(Math.round(box!.y)).toBe(10);
    const radius = await sky.evaluate((el) => getComputedStyle(el).borderTopLeftRadius);
    expect(radius).toBe('26px');
    await expect(page.locator('aside.column')).toBeVisible();
  } else {
    // Phone: the sky is full-bleed.
    expect(Math.round(box!.x)).toBe(0);
    expect(Math.round(box!.width)).toBe(viewport.width);
    expect(Math.round(box!.height)).toBe(viewport.height);
  }
  await page.screenshot({ path: `../docs/media/2026-10-28-skeleton-${info.project.name}.png` });
});
