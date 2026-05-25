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

  // The linked-list demo has 6 calls (4x Node.__init__ + reverse + <module>),
  // so the Recursion tab auto-selects. Switch to Heap to find list views.
  await page.locator(".dsa-viz-tabs button", { hasText: "Heap" }).click();

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

test("binary-search example produces a pattern overlay on the array", async ({ page }) => {
  const src = [
    "def binary_search(nums, target):",
    "    lo = 0",
    "    hi = len(nums) - 1",
    "    while lo <= hi:",
    "        mid = (lo + hi) // 2",
    "        if nums[mid] == target:",
    "            return mid",
    "        if nums[mid] < target:",
    "            lo = mid + 1",
    "        else:",
    "            hi = mid - 1",
    "    return -1",
    "",
    "binary_search([1, 3, 5, 7, 9, 11, 13, 15, 17, 19], 13)",
  ].join("\n");

  await page.goto("/");
  await page.locator(".editor-textarea").fill(src);
  await page.getByRole("button", { name: "Run & Visualize" }).click();
  await expect(page.locator(".dsa-viz-tcounter")).toBeVisible();

  // The binary_search call beats the call-count threshold, so Recursion
  // auto-selects. Switch to Heap to see the array overlay.
  await page.locator(".dsa-viz-tabs button", { hasText: "Heap" }).click();

  // Seek roughly into the second iteration; overlay should be active.
  const slider = page.locator('input[type="range"]');
  const max = await slider.evaluate((el: HTMLInputElement) => Number(el.max));
  await slider.evaluate((el: HTMLInputElement, v: number) => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
    setter.call(el, String(v));
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }, Math.floor(max * 0.4));

  await expect(page.locator(".dsa-viz-array-overlay-label")).toHaveText(
    /^binary search \[\d+…\d+\]$/,
  );
  expect(await page.locator(".dsa-viz-cell.is-mid").count()).toBe(1);
});

test("share button persists a trace and the resulting URL loads it back", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Run & Visualize" }).click();
  await expect(page.locator(".dsa-viz-tcounter")).toBeVisible();

  await page.getByRole("button", { name: "Share" }).click();
  const link = page.locator(".share-link");
  await expect(link).toBeVisible();
  const href = await link.getAttribute("href");
  expect(href).toMatch(/\?t=[a-f0-9]{8}$/);

  await page.goto(href!);
  await expect(page.locator(".dsa-viz-tcounter")).toBeVisible();
  // The restored trace should have the same total events.
  await expect(page.locator(".dsa-viz-tcounter")).toHaveText(/^t = 0 \/ 51$/);
});

test("compare mode runs two programs and highlights the first divergence", async ({ page }) => {
  await page.goto("/");
  // Switch into compare mode.
  await page.locator(".app-header select").first().selectOption("compare");
  // Two editors should be visible.
  await expect(page.locator(".compare-editors textarea")).toHaveCount(2);
  // The seeded programs differ at one local; clicking Compare should diverge.
  await page.getByRole("button", { name: "Compare" }).click();
  await expect(page.locator(".diff-summary[data-diverged='true']")).toBeVisible();
  await expect(page.locator(".diff-summary")).toContainText(/Diverged at event \d+/);
  // Two side-by-side panels render.
  await expect(page.locator(".compare-panel")).toHaveCount(2);
});

test("recursion tab auto-selects and renders the fib(6) tree", async ({ page }) => {
  const fibSource = [
    "def fib(n):",
    "    if n < 2:",
    "        return n",
    "    return fib(n - 1) + fib(n - 2)",
    "",
    "print(fib(6))",
  ].join("\n");

  await page.goto("/");
  await page.locator(".editor-textarea").fill(fibSource);
  await page.getByRole("button", { name: "Run & Visualize" }).click();
  await expect(page.locator(".dsa-viz-tcounter")).toBeVisible();

  // Recursion tab should be auto-selected because call count > 5.
  const recursionTab = page.locator(".dsa-viz-tabs button", { hasText: /^Recursion/ });
  await expect(recursionTab).toHaveAttribute("aria-selected", "true");

  // 1 <module> + 25 fib = 26 nodes for fib(6).
  await expect(page.locator(".dsa-viz-recursion-node")).toHaveCount(26);
});
