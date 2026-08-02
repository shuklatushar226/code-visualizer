import { test, expect } from "@playwright/test";

test("standalone bundle mounts VisualizerPanel with a hardcoded trace", async ({ page }) => {
  await page.goto("/smoke.html");

  // The fixture imports standalone.mjs and calls mountVisualizer.
  await expect(page.locator(".dsa-viz-panel")).toBeVisible();
  await expect(page.locator(".dsa-viz-codeline")).toHaveCount(3);
  // The panel opens at the first event with inspectable state.
  await expect(page.locator(".dsa-viz-tcounter")).toHaveText("t = 1 / 3");

  // Stepping the playback updates the cursor (last "▶" button = Step forward).
  await page.locator('.dsa-viz-buttons button[title="Step forward"]').click();
  await expect(page.locator(".dsa-viz-tcounter")).toHaveText("t = 2 / 3");

  // The handle API is exposed for embedders.
  const hasHandle = await page.evaluate(() => typeof (window as any).__handle?.unmount === "function");
  expect(hasHandle).toBe(true);
});
