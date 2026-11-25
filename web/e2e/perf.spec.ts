import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

// Opt-in: `WORKS_PERF=1 npx playwright test e2e/perf.spec.ts`. It measures the queue's first
// render and fails on a console error, so the React Compiler build is compared on behaviour too.
const PERF = process.env.WORKS_PERF === "1";
const STATE = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", ".e2e-state.json");

function appPath(): string {
  const { token } = JSON.parse(readFileSync(STATE, "utf8")) as { token?: string };
  return token ? `/?bootstrap=${encodeURIComponent(token)}` : "/";
}

test("the queue renders without console errors", async ({ page }) => {
  test.skip(!PERF, "opt-in: set WORKS_PERF=1");
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(String(error)));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });

  const started = Date.now();
  await page.goto(appPath());
  await expect(page.getByRole("complementary", { name: "Queue" })).toBeVisible();
  const firstRender = Date.now() - started;

  expect(errors, errors.join("\n")).toEqual([]);
  expect(firstRender).toBeLessThan(5000);
  console.log(`queue first render: ${firstRender} ms`);
});
