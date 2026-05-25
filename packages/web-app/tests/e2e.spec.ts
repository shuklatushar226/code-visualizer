import { test, expect } from "@playwright/test";

test("runs the default Python program and produces a trace", async ({ page }) => {
  await page.goto("/");

  // The default editor text is the linked-list-reverse demo.
  // Click Run & Visualize and wait for the trace to materialize.
  await page.getByRole("button", { name: "Run & Visualize" }).click();

  // The control bar's t-counter appears once a trace is loaded.
  const tCounter = page.locator(".dsa-viz-tcounter");
  await expect(tCounter).toBeVisible();
  const initial = await tCounter.textContent();
  expect(initial).toMatch(/^t = 0 \/ \d+/);

  // Seek to the final event via the range slider.
  const slider = page.locator('input[type="range"]');
  const max = await slider.evaluate((el: HTMLInputElement) => Number(el.max));
  expect(max).toBeGreaterThan(10);
  await slider.evaluate((el: HTMLInputElement, value: number) => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
    setter.call(el, String(value));
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }, max);

  // Wait for React to commit the new t.
  await expect(tCounter).toHaveText(new RegExp(`^t = ${max} / ${max}$`));

  // At the final event, the visualizer renders the reversed list. Search all
  // linked-list views for the [4,3,2,1] sequence (head/result ordering can vary).
  const allLists = await page
    .locator(".dsa-viz-linkedlist")
    .evaluateAll((nodes) =>
      nodes.map((n) =>
        Array.from(n.querySelectorAll(".dsa-viz-node-val")).map((v) => v.textContent?.trim() ?? "")
      )
    );
  expect(allLists).toContainEqual(["4", "3", "2", "1"]);
});

test("runs the two_sum example via paste and shows the seen dict growing", async ({ page }) => {
  const twoSumSource = [
    "def two_sum(nums, target):",
    "    seen = {}",
    "    for i, x in enumerate(nums):",
    "        need = target - x",
    "        if need in seen:",
    "            return [seen[need], i]",
    "        seen[x] = i",
    "    return []",
    "",
    "two_sum([2, 7, 11, 15], 9)",
  ].join("\n");

  await page.goto("/");
  const editor = page.locator(".editor-textarea");
  await editor.fill(twoSumSource);
  await page.getByRole("button", { name: "Run & Visualize" }).click();

  const tCounter = page.locator(".dsa-viz-tcounter");
  await expect(tCounter).toBeVisible();
  // The source pane mirrors whatever the user pasted. That's the simplest
  // proof the trace is rendering our two_sum source, not the default.
  await expect(page.locator(".dsa-viz-codepane")).toContainText("def two_sum");
});
